import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import record_audit
from core.serialization import json_safe
from fleet.models import (
    Accessory,
    Asset,
    EquipmentCategory,
    EquipmentModel,
    Location,
    MeterReading,
)

from .models import ImportBatch, ImportChange, ImportRow
from .parsers import ImportFileError, parse_import_file

logger = logging.getLogger(__name__)
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class RowValidation:
    data: dict
    action: str = str(ImportRow.Action.CREATE)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    obj: object | None = None

    def fail(self, message):
        self.errors.append(message)
        self.action = ImportRow.Action.ERROR
        return self


def file_sha256(upload):
    digest = hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def _text(value):
    return str(value or "").strip()


def _required(result, data, key, label):
    value = _text(data.get(key))
    if not value:
        result.fail(f"{label} is required.")
    return value


def _require_identifier(result, data, key, label):
    value = _required(result, data, key, label).upper()
    if value and not IDENTIFIER_PATTERN.fullmatch(value):
        result.fail(
            f"{label} may only contain letters, numbers, dots, hyphens and underscores."
        )
    return value


def _as_decimal(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _decimal(value, label, result, required=False):
    text = _text(value)
    if not text:
        if required:
            result.fail(f"{label} is required.")
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        result.fail(f"{label} must be a number.")
        return None
    if parsed < 0:
        result.fail(f"{label} cannot be negative.")
    return parsed


def _boolean(value, default=True):
    text = _text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "active"}


def _date(value, label, result):
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        result.fail(f"{label} must use YYYY-MM-DD.")
        return None


def _datetime(value, label, result):
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        result.fail(f"{label} must be an ISO date/time.")
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _duplicate_action(result, existing, batch):
    if result.errors:
        result.action = ImportRow.Action.ERROR
        return
    if existing is None:
        result.action = ImportRow.Action.CREATE
        result.obj = None
        return
    result.obj = existing
    if batch.duplicate_policy == ImportBatch.DuplicatePolicy.UPDATE:
        result.action = ImportRow.Action.UPDATE
    elif batch.duplicate_policy == ImportBatch.DuplicatePolicy.SKIP:
        result.action = ImportRow.Action.SKIP
        result.warnings.append("Existing record will be skipped.")
    else:
        result.fail("A matching record already exists.")


def _validate_location(row, batch, state):
    result = RowValidation(data={})
    code = _require_identifier(result, row, "code", "Location code")
    name = _required(result, row, "name", "Location name")
    location_type = _text(row.get("location_type")) or Location.Type.WAREHOUSE
    if location_type not in Location.Type.values:
        result.fail("Location type is invalid.")
    result.data = {
        "code": code,
        "name": name,
        "location_type": location_type,
        "address": _text(row.get("address")),
        "is_active": _boolean(row.get("is_active"), True),
    }
    existing = Location.objects.filter(code=code).first() if code else None
    _duplicate_action(result, existing, batch)
    return result


def _validate_equipment_model(row, batch, state):
    result = RowValidation(data={})
    code = _require_identifier(result, row, "code", "Model code")
    name = _required(result, row, "name", "Model name")
    category_code = _required(result, row, "category_code", "Category code").lower()
    category = (
        EquipmentCategory.objects.filter(code=category_code).first()
        if category_code
        else None
    )
    if category is None and category_code:
        result.fail(f"Category '{category_code}' does not exist.")
    specifications = {}
    raw_specifications = _text(row.get("specifications_json"))
    if raw_specifications:
        try:
            specifications = json.loads(raw_specifications)
        except json.JSONDecodeError:
            result.fail("Specifications JSON is invalid.")
        if not isinstance(specifications, dict):
            result.fail("Specifications JSON must be an object.")
    result.data = {
        "code": code,
        "name": name,
        "category_id": category.pk if category else None,
        "manufacturer": _text(row.get("manufacturer")),
        "model_number": _text(row.get("model_number")),
        "specifications": specifications,
        "is_active": _boolean(row.get("is_active"), True),
    }
    existing = EquipmentModel.objects.filter(code=code).first() if code else None
    _duplicate_action(result, existing, batch)
    return result


def _validate_asset(row, batch, state):
    result = RowValidation(data={})
    asset_number = _require_identifier(result, row, "asset_number", "Asset number")
    model_code = _required(result, row, "model_code", "Equipment model code").upper()
    model = (
        EquipmentModel.objects.filter(code=model_code).first() if model_code else None
    )
    if model is None and model_code:
        result.fail(f"Equipment model '{model_code}' does not exist.")
    location_code = _text(row.get("location_code")).upper()
    location = (
        Location.objects.filter(code=location_code).first() if location_code else None
    )
    if location_code and location is None:
        result.fail(f"Location '{location_code}' does not exist.")
    serial_number = _text(row.get("serial_number"))
    qr_code = _text(row.get("qr_code"))
    existing = Asset.objects.filter(asset_number=asset_number).first()
    if serial_number:
        serial_qs = Asset.objects.filter(serial_number=serial_number)
        if existing:
            serial_qs = serial_qs.exclude(pk=existing.pk)
        if serial_qs.exists():
            result.fail("Serial number is already used by another asset.")
    if qr_code:
        qr_qs = Asset.objects.filter(qr_code=qr_code)
        if existing:
            qr_qs = qr_qs.exclude(pk=existing.pk)
        if qr_qs.exists():
            result.fail("QR code is already used by another asset.")
    current_hours = _decimal(row.get("current_hours"), "Current hours", result)
    current_kilometers = _decimal(
        row.get("current_kilometers"), "Current kilometres", result
    )
    result.data = {
        "asset_number": asset_number,
        "model_id": model.pk if model else None,
        "location_id": location.pk if location else None,
        "serial_number": serial_number,
        "registration_number": _text(row.get("registration_number")),
        "qr_code": qr_code,
        "current_hours": current_hours,
        "current_kilometers": current_kilometers,
        "acquired_on": _date(row.get("acquired_on"), "Acquired date", result),
        "purchase_cost": _decimal(row.get("purchase_cost"), "Purchase cost", result),
        "notes": _text(row.get("notes")),
    }
    _duplicate_action(result, existing, batch)
    if existing is not None:
        if current_hours is not None and current_hours != existing.current_hours:
            result.warnings.append("Current hours are not changed by an asset import.")
        if (
            current_kilometers is not None
            and current_kilometers != existing.current_kilometers
        ):
            result.warnings.append(
                "Current kilometres are not changed by an asset import."
            )
    return result


def _validate_accessory(row, batch, state):
    result = RowValidation(data={})
    code = _require_identifier(result, row, "code", "Accessory code")
    name = _required(result, row, "name", "Accessory name")
    location_code = _text(row.get("location_code")).upper()
    location = (
        Location.objects.filter(code=location_code).first() if location_code else None
    )
    if location_code and location is None:
        result.fail(f"Location '{location_code}' does not exist.")
    model_codes = [
        code.strip().upper()
        for code in _text(row.get("compatible_model_codes")).split(",")
        if code.strip()
    ]
    compatible_models = list(EquipmentModel.objects.filter(code__in=model_codes))
    if len(compatible_models) != len(set(model_codes)):
        found = {model.code for model in compatible_models}
        result.fail(
            "Unknown compatible model code(s): "
            + ", ".join(sorted(set(model_codes) - found))
        )
    status = _text(row.get("status")) or Accessory.Status.AVAILABLE
    if status not in Accessory.Status.values:
        result.fail("Accessory status is invalid.")
    result.data = {
        "code": code,
        "name": name,
        "accessory_type": _text(row.get("accessory_type")),
        "serial_number": _text(row.get("serial_number")),
        "location_id": location.pk if location else None,
        "compatible_model_ids": [model.pk for model in compatible_models],
        "status": status,
        "notes": _text(row.get("notes")),
    }
    existing = Accessory.objects.filter(code=code).first() if code else None
    _duplicate_action(result, existing, batch)
    return result


def _validate_meter_reading(row, batch, state):
    result = RowValidation(data={})
    asset_number = _required(result, row, "asset_number", "Asset number").upper()
    asset = (
        Asset.objects.filter(asset_number=asset_number).first()
        if asset_number
        else None
    )
    if asset is None and asset_number:
        result.fail(f"Asset '{asset_number}' does not exist.")
    hours = _decimal(row.get("hours"), "Hours", result)
    kilometers = _decimal(row.get("kilometers"), "Kilometres", result)
    if hours is None and kilometers is None and not result.errors:
        result.fail("At least hours or kilometres is required.")
    recorded_at = _datetime(row.get("recorded_at"), "Recorded at", result)
    if recorded_at is None:
        result.fail("Recorded at is required.")
    source = _text(row.get("source")) or MeterReading.Source.IMPORT
    if source not in MeterReading.Source.values:
        result.fail("Meter reading source is invalid.")
    if asset:
        if hours is not None and hours < asset.current_hours:
            result.fail("Hours cannot move backwards from the current reading.")
        if kilometers is not None and kilometers < asset.current_kilometers:
            result.fail("Kilometres cannot move backwards from the current reading.")
        if (
            recorded_at
            and MeterReading.objects.filter(
                asset=asset, recorded_at=recorded_at, source=source
            ).exists()
        ):
            result.fail("This meter reading already exists.")
        previous = state.setdefault(
            "meter_readings",
            {asset.pk: (asset.current_hours, asset.current_kilometers)},
        ).get(asset.pk)
        if previous:
            previous_hours, previous_km = previous
            if hours is not None and hours < previous_hours:
                result.fail("Hours move backwards within the file.")
            if kilometers is not None and kilometers < previous_km:
                result.fail("Kilometres move backwards within the file.")
            state["meter_readings"][asset.pk] = (
                hours if hours is not None else previous_hours,
                kilometers if kilometers is not None else previous_km,
            )
    result.data = {
        "asset_id": asset.pk if asset else None,
        "hours": hours,
        "kilometers": kilometers,
        "recorded_at": recorded_at,
        "source": source,
        "notes": _text(row.get("notes")),
    }
    result.action = ImportRow.Action.CREATE
    return result


VALIDATORS = {
    ImportBatch.Type.LOCATION: _validate_location,
    ImportBatch.Type.EQUIPMENT_MODEL: _validate_equipment_model,
    ImportBatch.Type.ASSET: _validate_asset,
    ImportBatch.Type.ACCESSORY: _validate_accessory,
    ImportBatch.Type.METER_READING: _validate_meter_reading,
}


def _apply_asset_quota(batch, results):
    if batch.import_type != ImportBatch.Type.ASSET:
        return
    tenant = batch.tenant
    if tenant.plan.max_assets is None:
        return
    slots = max(0, tenant.plan.max_assets - Asset.objects.count())
    for result in results:
        if result.action != ImportRow.Action.CREATE:
            continue
        if slots:
            slots -= 1
        else:
            result.fail(f"Plan '{tenant.plan.code}' asset quota has been reached.")


@transaction.atomic
def validate_import_batch(batch, *, actor=None):
    batch = (
        ImportBatch.objects.select_for_update()
        .select_related("tenant__plan")
        .get(pk=batch.pk)
    )
    if batch.status not in {
        ImportBatch.Status.UPLOADED,
        ImportBatch.Status.FAILED,
    }:
        raise ValidationError({"status": "This import cannot be validated again."})
    batch.status = ImportBatch.Status.VALIDATING
    batch.failure_message = ""
    batch.save(update_fields=["status", "failure_message", "updated_at"])

    try:
        _, rows = parse_import_file(batch)
        batch.rows.all().delete()
        batch.changes.all().delete()
        validator = VALIDATORS[batch.import_type]
        state = {}
        results = []
        duplicate_keys = set()
        for row_number, raw_data, normalized_data in rows:
            result = validator(normalized_data, batch, state)
            key = None
            if batch.import_type == ImportBatch.Type.LOCATION:
                key = normalized_data.get("code", "").strip().upper()
            elif batch.import_type == ImportBatch.Type.EQUIPMENT_MODEL:
                key = normalized_data.get("code", "").strip().upper()
            elif batch.import_type == ImportBatch.Type.ASSET:
                key = normalized_data.get("asset_number", "").strip().upper()
            elif batch.import_type == ImportBatch.Type.ACCESSORY:
                key = normalized_data.get("code", "").strip().upper()
            elif batch.import_type == ImportBatch.Type.METER_READING:
                key = (
                    normalized_data.get("asset_number", "").strip().upper(),
                    normalized_data.get("recorded_at", ""),
                    normalized_data.get("source", ""),
                )
            if key and key in duplicate_keys:
                result.fail("Duplicate key appears more than once in the file.")
            elif key:
                duplicate_keys.add(key)
            results.append((row_number, raw_data, result))

        _apply_asset_quota(batch, [result for _, _, result in results])
        import_rows = []
        for row_number, raw_data, result in results:
            object_type = ""
            object_id = ""
            if result.obj is not None:
                object_type = result.obj._meta.label_lower
                object_id = str(result.obj.pk)
            import_rows.append(
                ImportRow(
                    batch=batch,
                    row_number=row_number,
                    raw_data=json_safe(raw_data),
                    normalized_data=json_safe(result.data),
                    validation_errors=result.errors,
                    warnings=result.warnings,
                    action=result.action,
                    object_type=object_type,
                    object_id=object_id,
                )
            )
        ImportRow.objects.bulk_create(import_rows)

        batch.total_rows = len(import_rows)
        batch.error_rows = sum(
            1 for row in import_rows if row.action == ImportRow.Action.ERROR
        )
        batch.warning_rows = sum(1 for row in import_rows if row.warnings)
        batch.valid_rows = batch.total_rows - batch.error_rows
        summary = {
            action: sum(1 for row in import_rows if row.action == action)
            for action in ImportRow.Action.values
        }
        if batch.summary.get("duplicate_file_of"):
            summary["duplicate_file_of"] = batch.summary["duplicate_file_of"]
        batch.summary = summary
        batch.status = ImportBatch.Status.PREVIEW_READY
        batch.validated_at = timezone.now()
        batch.save(
            update_fields=[
                "total_rows",
                "error_rows",
                "warning_rows",
                "valid_rows",
                "summary",
                "status",
                "validated_at",
                "updated_at",
            ]
        )
        record_audit(
            "import.validated",
            actor=actor,
            obj=batch,
            total_rows=batch.total_rows,
            error_rows=batch.error_rows,
        )
        return batch
    except ImportFileError as exc:
        batch.status = ImportBatch.Status.FAILED
        batch.failure_message = str(exc)
        batch.save(update_fields=["status", "failure_message", "updated_at"])
        record_audit(
            "import.validation_failed",
            actor=actor,
            obj=batch,
            reason=str(exc),
        )
        return batch
    except Exception as exc:
        logger.exception("Import validation failed", extra={"batch_id": batch.pk})
        batch.status = ImportBatch.Status.FAILED
        batch.failure_message = f"Validation failed: {exc}"
        batch.save(update_fields=["status", "failure_message", "updated_at"])
        record_audit(
            "import.validation_failed",
            actor=actor,
            obj=batch,
            reason=batch.failure_message,
        )
        return batch


def _snapshot(obj, field_names):
    if obj is None:
        return {}
    data = {}
    for field_name in field_names:
        value = getattr(obj, field_name)
        data[field_name] = value.pk if hasattr(value, "pk") else value
    return json_safe(data)


def _create_change(row, *, action, obj, before_data, after_data):
    return ImportChange.objects.create(
        batch=row.batch,
        import_row=row,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        object_label=str(obj),
        before_data=json_safe(before_data),
        after_data=json_safe(after_data),
    )


def _execute_row(row, actor):
    data = row.normalized_data
    import_type = row.batch.import_type
    before = {}
    if import_type == ImportBatch.Type.LOCATION:
        obj = (
            Location.objects.filter(pk=row.object_id).first() if row.object_id else None
        )
        before = _snapshot(
            obj, ("code", "name", "location_type", "address", "is_active")
        )
        if obj is None:
            obj = Location(**data)
        else:
            for key, value in data.items():
                setattr(obj, key, value)
        obj.save()
    elif import_type == ImportBatch.Type.EQUIPMENT_MODEL:
        obj = (
            EquipmentModel.objects.filter(pk=row.object_id).first()
            if row.object_id
            else None
        )
        before = _snapshot(
            obj,
            (
                "code",
                "name",
                "category_id",
                "manufacturer",
                "model_number",
                "specifications",
                "is_active",
            ),
        )
        if obj is None:
            obj = EquipmentModel(**data)
        else:
            for key, value in data.items():
                setattr(obj, key, value)
        obj.save()
    elif import_type == ImportBatch.Type.ASSET:
        obj = Asset.objects.filter(pk=row.object_id).first() if row.object_id else None
        before = _snapshot(
            obj,
            (
                "asset_number",
                "model_id",
                "location_id",
                "serial_number",
                "registration_number",
                "qr_code",
                "acquired_on",
                "purchase_cost",
                "notes",
            ),
        )
        if obj is None:
            obj = Asset(
                asset_number=data["asset_number"],
                model_id=data["model_id"],
                location_id=data["location_id"],
                serial_number=data["serial_number"],
                registration_number=data["registration_number"],
                qr_code=data["qr_code"],
                current_hours=_as_decimal(data["current_hours"]) or Decimal("0"),
                current_kilometers=(
                    _as_decimal(data["current_kilometers"]) or Decimal("0")
                ),
                acquired_on=data["acquired_on"],
                purchase_cost=_as_decimal(data["purchase_cost"]),
                notes=data["notes"],
                created_by=actor,
            )
        else:
            for key in (
                "model_id",
                "location_id",
                "serial_number",
                "registration_number",
                "qr_code",
                "acquired_on",
                "purchase_cost",
                "notes",
            ):
                setattr(
                    obj,
                    key,
                    _as_decimal(data[key]) if key == "purchase_cost" else data[key],
                )
        obj.save()
    elif import_type == ImportBatch.Type.ACCESSORY:
        obj = (
            Accessory.objects.filter(pk=row.object_id).first()
            if row.object_id
            else None
        )
        before = _snapshot(
            obj,
            (
                "code",
                "name",
                "accessory_type",
                "serial_number",
                "location_id",
                "status",
                "notes",
            ),
        )
        data_without_models = {
            key: value for key, value in data.items() if key != "compatible_model_ids"
        }
        if obj is None:
            obj = Accessory(**data_without_models)
        else:
            for key, value in data_without_models.items():
                setattr(obj, key, value)
        obj.save()
        obj.compatible_models.set(data["compatible_model_ids"])
    elif import_type == ImportBatch.Type.METER_READING:
        obj = MeterReading(
            asset_id=data["asset_id"],
            hours=_as_decimal(data["hours"]),
            kilometers=_as_decimal(data["kilometers"]),
            recorded_at=data["recorded_at"],
            source=data["source"],
            notes=data["notes"],
            actor=actor,
        )
        obj.save()
    else:
        raise ValidationError("Unsupported import type.")

    action = (
        ImportChange.Action.CREATE
        if row.action == ImportRow.Action.CREATE
        else ImportChange.Action.UPDATE
    )
    _create_change(
        row,
        action=action,
        obj=obj,
        before_data=before,
        after_data=_snapshot(obj, [field.name for field in obj._meta.fields]),
    )
    row.object_type = obj._meta.label_lower
    row.object_id = str(obj.pk)
    row.save(update_fields=["object_type", "object_id"])
    return action


def commit_import_batch(batch, *, actor):
    try:
        with transaction.atomic():
            batch = (
                ImportBatch.objects.select_for_update()
                .select_related("tenant__plan")
                .get(pk=batch.pk)
            )
            if not batch.can_commit:
                raise ValidationError(
                    {"status": "Import must have a preview and zero errors."}
                )
            batch.status = ImportBatch.Status.COMMITTING
            batch.save(update_fields=["status", "updated_at"])
            created = 0
            updated = 0
            skipped = 0
            for row in batch.rows.select_related("batch"):
                if row.action == ImportRow.Action.SKIP:
                    skipped += 1
                    continue
                if row.action == ImportRow.Action.ERROR:
                    raise ValidationError(
                        f"Row {row.row_number} still has validation errors."
                    )
                change_action = _execute_row(row, actor)
                if change_action == ImportChange.Action.CREATE:
                    created += 1
                else:
                    updated += 1
            batch.created_rows = created
            batch.updated_rows = updated
            batch.skipped_rows = skipped
            batch.status = ImportBatch.Status.COMPLETED
            batch.committed_by = actor
            batch.committed_at = timezone.now()
            batch.save(
                update_fields=[
                    "created_rows",
                    "updated_rows",
                    "skipped_rows",
                    "status",
                    "committed_by",
                    "committed_at",
                    "updated_at",
                ]
            )
            record_audit(
                "import.committed",
                actor=actor,
                obj=batch,
                created=created,
                updated=updated,
                skipped=skipped,
            )
            return batch
    except Exception as exc:
        ImportBatch.objects.filter(pk=batch.pk).update(
            status=ImportBatch.Status.FAILED,
            failure_message=str(exc),
            updated_at=timezone.now(),
        )
        raise


def cancel_import_batch(batch, *, actor):
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
        if batch.status not in {
            ImportBatch.Status.UPLOADED,
            ImportBatch.Status.FAILED,
            ImportBatch.Status.PREVIEW_READY,
        }:
            raise ValidationError({"status": "Import cannot be cancelled."})
        batch.status = ImportBatch.Status.CANCELLED
        batch.save(update_fields=["status", "updated_at"])
        record_audit("import.cancelled", actor=actor, obj=batch)
        return batch


def undo_import_batch(batch, *, actor):
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
        if not batch.can_undo:
            raise ValidationError(
                {"status": "Only create-only completed imports can be undone."}
            )
        changes = list(
            batch.changes.select_related("import_row").order_by("-created_at", "-id")
        )
        from rentals.models import QuoteLine, RentalLine

        for change in changes:
            if change.object_type == "fleet.asset":
                asset = Asset.objects.filter(pk=change.object_id).first()
                if asset is None:
                    continue
                if (
                    asset.reservations.exists()
                    or QuoteLine.objects.filter(asset=asset).exists()
                    or RentalLine.objects.filter(asset=asset).exists()
                    or asset.meter_readings.exclude(
                        source=MeterReading.Source.IMPORT
                    ).exists()
                ):
                    raise ValidationError(
                        {"status": "Imported asset has since been used."}
                    )
                asset.transition_to(
                    Asset.Status.RETIRED,
                    actor=actor,
                    reason=f"Undo import batch {batch.pk}",
                    source="import_undo",
                )
            elif change.object_type == "fleet.location":
                location = Location.objects.filter(pk=change.object_id).first()
                if location is None:
                    continue
                if location.assets.exists() or location.accessories.exists():
                    raise ValidationError(
                        {"status": "Imported location now has assigned records."}
                    )
                location.delete()
            elif change.object_type == "fleet.equipmentmodel":
                model = EquipmentModel.objects.filter(pk=change.object_id).first()
                if model is None:
                    continue
                if (
                    model.assets.exists()
                    or model.rate_components.exists()
                    or QuoteLine.objects.filter(equipment_model=model).exists()
                    or RentalLine.objects.filter(equipment_model=model).exists()
                ):
                    raise ValidationError(
                        {"status": "Imported model is now referenced."}
                    )
                model.delete()
            elif change.object_type == "fleet.accessory":
                accessory = Accessory.objects.filter(pk=change.object_id).first()
                if accessory is not None:
                    accessory.delete()
        batch.status = ImportBatch.Status.UNDONE
        batch.save(update_fields=["status", "updated_at"])
        record_audit("import.undone", actor=actor, obj=batch)
        return batch
