from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import record_audit
from fleet.models import Asset

from .models import (
    AssetLogisticsEvent,
    DeliveryReceipt,
    InventoryCount,
    InventoryCountLine,
    TransportJob,
    TransportJobAsset,
)


def resolve_asset(identifier):
    value = str(identifier or "").strip()
    if not value:
        raise ValidationError({"asset_identifier": "Asset identifier is required."})
    query = (
        Q(qr_code__iexact=value)
        | Q(asset_number__iexact=value)
        | Q(serial_number__iexact=value)
    )
    if value.isdigit():
        query |= Q(pk=int(value))
    asset = Asset.objects.filter(query).first()
    if asset is None:
        raise ValidationError(
            {"asset_identifier": f"Asset '{value}' was not found in this tenant."}
        )
    return asset


def _event_for_client(client_event_id):
    if client_event_id is None:
        return None
    return AssetLogisticsEvent.objects.filter(client_event_id=client_event_id).first()


def _ensure_job_asset(job, asset):
    if job and not TransportJobAsset.objects.filter(job=job, asset=asset).exists():
        raise ValidationError({"asset": "Asset is not assigned to this transport job."})


def _transition_if_possible(asset, target, *, actor, reason, source):
    if asset.status == target:
        return
    if target not in Asset.ALLOWED_TRANSITIONS.get(asset.status, set()):
        return
    asset.transition_to(target, actor=actor, reason=reason, source=source)
    asset.refresh_from_db()


def _apply_event_to_asset(event):
    asset = event.asset
    direction = event.job.direction if event.job_id else ""
    source = f"logistics:{event.source}"
    reason = (
        f"{event.get_event_type_display()} {event.job.number if event.job_id else ''}"
    )

    if event.event_type == AssetLogisticsEvent.Type.PREPARE:
        _transition_if_possible(
            asset,
            Asset.Status.READY_FOR_DISPATCH,
            actor=event.actor,
            reason=reason,
            source=source,
        )
    elif event.event_type == AssetLogisticsEvent.Type.LOAD:
        if direction in {
            TransportJob.Direction.OUTBOUND,
            TransportJob.Direction.INBOUND,
        }:
            if asset.status in {Asset.Status.RESERVED, Asset.Status.PREPARING}:
                _transition_if_possible(
                    asset,
                    Asset.Status.READY_FOR_DISPATCH,
                    actor=event.actor,
                    reason=reason,
                    source=source,
                )
            if asset.status in {
                Asset.Status.READY_FOR_DISPATCH,
                Asset.Status.PENDING_COLLECTION,
            }:
                _transition_if_possible(
                    asset,
                    Asset.Status.IN_TRANSIT,
                    actor=event.actor,
                    reason=reason,
                    source=source,
                )
    elif event.event_type in {
        AssetLogisticsEvent.Type.ARRIVE_SITE,
        AssetLogisticsEvent.Type.UNLOAD,
        AssetLogisticsEvent.Type.DELIVER,
    }:
        if asset.status == Asset.Status.IN_TRANSIT:
            _transition_if_possible(
                asset,
                Asset.Status.ON_SITE,
                actor=event.actor,
                reason=reason,
                source=source,
            )
        if event.event_type != AssetLogisticsEvent.Type.UNLOAD:
            asset.location = None
            asset.save(update_fields=["location", "updated_at"])
    elif event.event_type == AssetLogisticsEvent.Type.COLLECT_REQUEST:
        if asset.status in {Asset.Status.ON_SITE, Asset.Status.PAUSED}:
            _transition_if_possible(
                asset,
                Asset.Status.PENDING_COLLECTION,
                actor=event.actor,
                reason=reason,
                source=source,
            )
    elif event.event_type == AssetLogisticsEvent.Type.COLLECT:
        if asset.status == Asset.Status.ON_SITE:
            _transition_if_possible(
                asset,
                Asset.Status.PENDING_COLLECTION,
                actor=event.actor,
                reason=reason,
                source=source,
            )
        if asset.status == Asset.Status.PENDING_COLLECTION:
            _transition_if_possible(
                asset,
                Asset.Status.IN_TRANSIT,
                actor=event.actor,
                reason=reason,
                source=source,
            )
    elif event.event_type == AssetLogisticsEvent.Type.RECEIVE_WAREHOUSE:
        if asset.status in {Asset.Status.IN_TRANSIT, Asset.Status.PENDING_COLLECTION}:
            _transition_if_possible(
                asset,
                Asset.Status.RETURN_INSPECTION,
                actor=event.actor,
                reason=reason,
                source=source,
            )
        target_location = event.to_location or (
            event.job.depot if event.job_id else None
        )
        if target_location:
            asset.location = target_location
            asset.save(update_fields=["location", "updated_at"])
    elif event.event_type == AssetLogisticsEvent.Type.TRANSFER:
        if event.to_location is None:
            raise ValidationError({"to_location": "Transfer requires a destination."})
        asset.location = event.to_location
        asset.save(update_fields=["location", "updated_at"])


def _apply_event_to_job(event):
    job = event.job
    if job is None:
        return
    changed = set()
    if event.event_type in {
        AssetLogisticsEvent.Type.LOAD,
        AssetLogisticsEvent.Type.DEPART,
    }:
        if job.status == TransportJob.Status.SCHEDULED:
            job.status = TransportJob.Status.IN_PROGRESS
            changed.add("status")
        if job.actual_start is None:
            job.actual_start = event.occurred_at
            changed.add("actual_start")
        if event.event_type == AssetLogisticsEvent.Type.LOAD:
            TransportJobAsset.objects.filter(job=job, asset=event.asset).update(
                loaded_at=event.occurred_at
            )
    elif event.event_type == AssetLogisticsEvent.Type.ARRIVE_SITE:
        if job.status == TransportJob.Status.IN_PROGRESS:
            job.status = TransportJob.Status.AT_SITE
            changed.add("status")
        if job.actual_arrival is None:
            job.actual_arrival = event.occurred_at
            changed.add("actual_arrival")
    elif event.event_type == AssetLogisticsEvent.Type.DELIVER:
        if job.status in {
            TransportJob.Status.IN_PROGRESS,
            TransportJob.Status.AT_SITE,
        }:
            job.status = TransportJob.Status.DELIVERED
            changed.add("status")
        if job.actual_delivery is None:
            job.actual_delivery = event.occurred_at
            changed.add("actual_delivery")
        TransportJobAsset.objects.filter(job=job, asset=event.asset).update(
            delivered_at=event.occurred_at
        )
    elif event.event_type == AssetLogisticsEvent.Type.RECEIVE_WAREHOUSE:
        if job.status != TransportJob.Status.COMPLETED:
            job.status = TransportJob.Status.COMPLETED
            changed.add("status")
        if job.completed_at is None:
            job.completed_at = event.occurred_at
            changed.add("completed_at")
    if changed:
        changed.add("updated_at")
        job.save(update_fields=changed)


def record_asset_event(
    *,
    actor,
    event_type,
    asset_identifier=None,
    asset=None,
    job=None,
    from_location=None,
    to_location=None,
    site=None,
    latitude=None,
    longitude=None,
    occurred_at=None,
    source=AssetLogisticsEvent.Source.MOBILE,
    client_event_id=None,
    notes="",
    metadata=None,
):
    existing = _event_for_client(client_event_id)
    if existing is not None:
        return existing

    resolved_asset = asset or resolve_asset(asset_identifier)
    try:
        with transaction.atomic():
            locked_job = (
                TransportJob.objects.select_for_update().get(pk=job.pk)
                if job is not None
                else None
            )
            _ensure_job_asset(locked_job, resolved_asset)
            event = AssetLogisticsEvent.objects.create(
                job=locked_job,
                asset=resolved_asset,
                event_type=event_type,
                from_location=from_location or resolved_asset.location,
                to_location=to_location,
                site=site or (locked_job.destination_site if locked_job else None),
                latitude=latitude,
                longitude=longitude,
                occurred_at=occurred_at or timezone.now(),
                source=source,
                client_event_id=client_event_id,
                actor=actor,
                notes=notes,
                metadata=metadata or {},
            )
            _apply_event_to_asset(event)
            _apply_event_to_job(event)
            record_audit(
                "logistics.event.recorded",
                actor=actor,
                obj=event,
                asset=resolved_asset.asset_number,
                event_type=event_type,
                job=locked_job.number if locked_job else "",
            )
            return event
    except IntegrityError:
        existing = _event_for_client(client_event_id)
        if existing is not None:
            return existing
        raise


def record_delivery_receipt(
    *,
    actor,
    job,
    signer_name,
    accepted,
    signer_phone="",
    rejection_reason="",
    signature_data="",
    signed_at=None,
    latitude=None,
    longitude=None,
    client_event_id=None,
    notes="",
):
    if client_event_id:
        existing = DeliveryReceipt.objects.filter(
            client_event_id=client_event_id
        ).first()
        if existing is not None:
            return existing
    try:
        with transaction.atomic():
            locked_job = TransportJob.objects.select_for_update().get(pk=job.pk)
            if locked_job.status not in {
                TransportJob.Status.IN_PROGRESS,
                TransportJob.Status.AT_SITE,
                TransportJob.Status.DELIVERED,
            }:
                raise ValidationError(
                    {"job": "Receipt requires an in-progress or on-site delivery."}
                )
            receipt = DeliveryReceipt.objects.create(
                job=locked_job,
                signer_name=signer_name,
                signer_phone=signer_phone,
                accepted=accepted,
                rejection_reason=rejection_reason,
                signature_data=signature_data,
                signed_at=signed_at or timezone.now(),
                latitude=latitude,
                longitude=longitude,
                client_event_id=client_event_id,
                actor=actor,
                notes=notes,
            )
            if accepted:
                locked_job.status = TransportJob.Status.DELIVERED
                locked_job.actual_delivery = (
                    locked_job.actual_delivery or receipt.signed_at
                )
                locked_job.save(
                    update_fields=["status", "actual_delivery", "updated_at"]
                )
            record_audit(
                "logistics.receipt.recorded",
                actor=actor,
                obj=receipt,
                job=locked_job.number,
                accepted=accepted,
            )
            return receipt
    except IntegrityError:
        existing = DeliveryReceipt.objects.filter(
            client_event_id=client_event_id
        ).first()
        if existing is not None:
            return existing
        raise


def transition_job(job, *, actor, action, reason=""):
    with transaction.atomic():
        job = TransportJob.objects.select_for_update().get(pk=job.pk)
        now = timezone.now()
        if action == "start":
            if job.status != TransportJob.Status.SCHEDULED:
                raise ValidationError({"status": "Only scheduled jobs can start."})
            job.status = TransportJob.Status.IN_PROGRESS
            job.actual_start = now
            fields = ["status", "actual_start", "updated_at"]
        elif action == "arrive":
            if job.status != TransportJob.Status.IN_PROGRESS:
                raise ValidationError({"status": "Only in-progress jobs can arrive."})
            job.status = TransportJob.Status.AT_SITE
            job.actual_arrival = now
            fields = ["status", "actual_arrival", "updated_at"]
        elif action == "deliver":
            if job.status not in {
                TransportJob.Status.IN_PROGRESS,
                TransportJob.Status.AT_SITE,
            }:
                raise ValidationError(
                    {"status": "Only active site jobs can be delivered."}
                )
            job.status = TransportJob.Status.DELIVERED
            job.actual_delivery = now
            fields = ["status", "actual_delivery", "updated_at"]
        elif action == "complete":
            if job.status not in {
                TransportJob.Status.DELIVERED,
                TransportJob.Status.AT_SITE,
                TransportJob.Status.IN_PROGRESS,
            }:
                raise ValidationError(
                    {"status": "This transport job cannot be completed."}
                )
            if (
                job.direction == TransportJob.Direction.OUTBOUND
                and not job.receipts.filter(accepted=True).exists()
            ):
                raise ValidationError(
                    {"receipt": "Outbound delivery requires an accepted receipt."}
                )
            job.status = TransportJob.Status.COMPLETED
            job.completed_at = now
            fields = ["status", "completed_at", "updated_at"]
        elif action == "cancel":
            if job.status != TransportJob.Status.SCHEDULED:
                raise ValidationError(
                    {"status": "Only scheduled jobs can be cancelled."}
                )
            job.status = TransportJob.Status.CANCELLED
            fields = ["status", "notes", "updated_at"]
            if reason:
                job.notes = f"{job.notes}\nCancelled: {reason}".strip()
        else:
            raise ValidationError({"action": "Unknown transport action."})
        job.save(update_fields=fields)
        record_audit(
            f"logistics.job.{action}",
            actor=actor,
            obj=job,
            reason=reason,
        )
        return job


def scan_inventory(
    count,
    *,
    actor,
    asset_identifier=None,
    asset=None,
    client_event_id=None,
    notes="",
):
    with transaction.atomic():
        count = InventoryCount.objects.select_for_update().get(pk=count.pk)
        if count.status != InventoryCount.Status.IN_PROGRESS:
            raise ValidationError({"status": "Inventory count is not in progress."})
        if client_event_id:
            existing_event = _event_for_client(client_event_id)
            if existing_event is not None:
                return existing_event.asset
        resolved_asset = asset or resolve_asset(asset_identifier)
        result = (
            InventoryCountLine.Result.FOUND
            if resolved_asset.location_id == count.location_id
            else InventoryCountLine.Result.UNEXPECTED
        )
        line, created = InventoryCountLine.objects.get_or_create(
            count=count,
            asset=resolved_asset,
            defaults={
                "result": result,
                "scanned_at": timezone.now(),
                "scanned_by": actor,
                "notes": notes,
            },
        )
        if created:
            AssetLogisticsEvent.objects.create(
                asset=resolved_asset,
                event_type=AssetLogisticsEvent.Type.INVENTORY,
                from_location=resolved_asset.location,
                source=AssetLogisticsEvent.Source.SCAN,
                client_event_id=client_event_id,
                actor=actor,
                notes=notes,
                metadata={
                    "inventory_count_id": count.pk,
                    "inventory_count_number": count.number,
                    "result": result,
                },
            )
        return line.asset


def complete_inventory(count, *, actor):
    with transaction.atomic():
        count = InventoryCount.objects.select_for_update().get(pk=count.pk)
        if count.status != InventoryCount.Status.IN_PROGRESS:
            raise ValidationError({"status": "Inventory count is not in progress."})
        location_assets = list(Asset.objects.filter(location=count.location))
        found_ids = set(
            count.lines.filter(result=InventoryCountLine.Result.FOUND).values_list(
                "asset_id", flat=True
            )
        )
        for asset in location_assets:
            if asset.pk not in found_ids:
                InventoryCountLine.objects.get_or_create(
                    count=count,
                    asset=asset,
                    defaults={
                        "result": InventoryCountLine.Result.MISSING,
                        "scanned_at": timezone.now(),
                        "scanned_by": actor,
                    },
                )
        count.expected_assets = len(location_assets)
        count.found_assets = count.lines.filter(
            result=InventoryCountLine.Result.FOUND
        ).count()
        count.missing_assets = count.lines.filter(
            result=InventoryCountLine.Result.MISSING
        ).count()
        count.unexpected_assets = count.lines.filter(
            result=InventoryCountLine.Result.UNEXPECTED
        ).count()
        count.status = InventoryCount.Status.COMPLETED
        count.completed_by = actor
        count.completed_at = timezone.now()
        count.save(
            update_fields=[
                "expected_assets",
                "found_assets",
                "missing_assets",
                "unexpected_assets",
                "status",
                "completed_by",
                "completed_at",
                "updated_at",
            ]
        )
        record_audit(
            "logistics.inventory.completed",
            actor=actor,
            obj=count,
            found=count.found_assets,
            missing=count.missing_assets,
            unexpected=count.unexpected_assets,
        )
        return count
