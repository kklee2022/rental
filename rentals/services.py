import copy
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import record_audit
from core.sequences import next_document_number
from core.serialization import json_safe
from fleet.models import Asset
from pricing.services import calculate_line
from tenants.settings_service import get_number_prefix

from .models import (
    Contract,
    ContractVersion,
    Quote,
    RentalLine,
    RentalOrder,
    ReservationAllocation,
)

ACTIVE_ALLOCATION_STATUSES = {
    ReservationAllocation.Status.HELD,
    ReservationAllocation.Status.CONFIRMED,
}
ALLOCATABLE_ASSET_STATUSES = {
    Asset.Status.AVAILABLE,
    Asset.Status.RESERVED,
    Asset.Status.PREPARING,
    Asset.Status.READY_FOR_DISPATCH,
}


def _quote_snapshot(quote):
    return json_safe(
        {
            "quote_id": quote.pk,
            "number": quote.number,
            "customer_id": quote.customer_id,
            "customer_name": quote.customer.name,
            "site_id": quote.site_id,
            "site_name": quote.site.name if quote.site_id else None,
            "currency": quote.currency,
            "valid_until": quote.valid_until,
            "subtotal": str(quote.subtotal),
            "discount_total": str(quote.discount_total),
            "tax_total": str(quote.tax_total),
            "total": str(quote.total),
            "deposit_total": str(quote.deposit_total),
            "lines": [
                {
                    "id": line.pk,
                    "line_type": line.line_type,
                    "description": line.description,
                    "equipment_model_id": line.equipment_model_id,
                    "asset_id": line.asset_id,
                    "start_at": line.start_at,
                    "end_at": line.end_at,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price or 0),
                    "discount_amount": str(line.discount_amount),
                    "line_total": str(line.line_total),
                    "tax_amount": str(line.tax_amount),
                    "pricing": line.price_snapshot,
                }
                for line in quote.lines.select_related(
                    "equipment_model", "asset", "rate_plan"
                ).order_by("sort_order", "id")
            ],
        }
    )


@transaction.atomic
def recalculate_quote(quote, *, actor=None):
    quote = Quote.objects.select_for_update().get(pk=quote.pk)
    if quote.status not in {Quote.Status.DRAFT, Quote.Status.PENDING_APPROVAL}:
        raise ValidationError(
            {"status": "Only draft or pending quotes can be recalculated."}
        )
    lines = list(
        quote.lines.select_related(
            "equipment_model", "asset", "rate_plan"
        ).prefetch_related("rate_plan__components")
    )
    if not lines:
        raise ValidationError({"lines": "A quote requires at least one line."})

    subtotal = Decimal("0")
    discount_total = Decimal("0")
    tax_total = Decimal("0")
    total = Decimal("0")
    deposit_total = Decimal("0")
    for line in lines:
        result = calculate_line(line)
        line.quantity = Decimal(result["quantity"])
        line.unit_price = result["unit_price"]
        line.discount_amount = result["discount"]
        line.line_total = result["total"]
        line.tax_amount = result["tax"]
        line.price_snapshot = result
        line.save(
            update_fields=[
                "quantity",
                "unit_price",
                "discount_amount",
                "line_total",
                "tax_amount",
                "price_snapshot",
                "updated_at",
            ]
        )
        subtotal += Decimal(result["subtotal"])
        discount_total += Decimal(result["discount"])
        tax_total += Decimal(result["tax"])
        total += Decimal(result["total"])
        deposit_total += Decimal(result["deposit"])

    quote.subtotal = subtotal
    quote.discount_total = discount_total
    quote.tax_total = tax_total
    quote.total = total
    quote.deposit_total = deposit_total
    quote.currency = lines[0].price_snapshot.get("currency", "HKD")
    quote.save(
        update_fields=[
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "deposit_total",
            "currency",
            "updated_at",
        ]
    )
    record_audit(
        "quote.calculated",
        actor=actor,
        obj=quote,
        total=str(quote.total),
    )
    return quote


@transaction.atomic
def submit_quote(quote, *, actor=None):
    quote = recalculate_quote(quote, actor=actor)
    if quote.status not in {Quote.Status.DRAFT, Quote.Status.REJECTED}:
        raise ValidationError({"status": "Quote cannot be submitted."})
    quote.status = Quote.Status.PENDING_APPROVAL
    quote.rejected_reason = ""
    quote.save(update_fields=["status", "rejected_reason", "updated_at"])
    record_audit("quote.submitted", actor=actor, obj=quote)
    return quote


@transaction.atomic
def approve_quote(quote, *, actor):
    recalculate_quote(quote, actor=actor)
    quote = (
        Quote.objects.select_for_update(of=("self",))
        .select_related("customer", "site")
        .get(pk=quote.pk)
    )
    if quote.status != Quote.Status.PENDING_APPROVAL:
        raise ValidationError({"status": "Only pending quotes can be approved."})
    if quote.valid_until and quote.valid_until < timezone.localdate():
        quote.status = Quote.Status.EXPIRED
        quote.save(update_fields=["status", "updated_at"])
        raise ValidationError({"valid_until": "Quote has expired."})
    quote.price_snapshot = _quote_snapshot(quote)
    quote.status = Quote.Status.APPROVED
    quote.approved_by = actor
    quote.approved_at = timezone.now()
    quote.save(
        update_fields=[
            "price_snapshot",
            "status",
            "approved_by",
            "approved_at",
            "updated_at",
        ]
    )
    record_audit(
        "quote.approved",
        actor=actor,
        obj=quote,
        total=str(quote.total),
    )
    return quote


@transaction.atomic
def reject_quote(quote, *, actor, reason):
    quote = Quote.objects.select_for_update().get(pk=quote.pk)
    if quote.status != Quote.Status.PENDING_APPROVAL:
        raise ValidationError({"status": "Only pending quotes can be rejected."})
    quote.status = Quote.Status.REJECTED
    quote.rejected_reason = reason
    quote.save(update_fields=["status", "rejected_reason", "updated_at"])
    record_audit("quote.rejected", actor=actor, obj=quote, reason=reason)
    return quote


@transaction.atomic
def convert_quote_to_order(quote, *, actor):
    quote = (
        Quote.objects.select_for_update(of=("self",))
        .select_related("customer", "site")
        .get(pk=quote.pk)
    )
    if quote.status != Quote.Status.APPROVED:
        raise ValidationError({"status": "Only approved quotes can be converted."})
    if RentalOrder.objects.filter(quote=quote).exists():
        raise ValidationError({"quote": "Quote already has a rental order."})
    timed_lines = [
        line
        for line in quote.lines.select_related(
            "equipment_model", "asset", "rate_plan"
        ).prefetch_related("rate_plan__components")
        if line.start_at and line.end_at
    ]
    if not timed_lines:
        raise ValidationError(
            {"lines": "At least one time-based line is required to create an order."}
        )
    order = RentalOrder.objects.create(
        number=next_document_number("rental_order", get_number_prefix("rental")),
        quote=quote,
        customer=quote.customer,
        site=quote.site,
        start_at=min(line.start_at for line in timed_lines),
        end_at=max(line.end_at for line in timed_lines),
        currency=quote.currency,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        tax_total=quote.tax_total,
        total=quote.total,
        deposit_total=quote.deposit_total,
        price_snapshot=quote.price_snapshot,
        created_by=actor,
    )
    for source in quote.lines.all().order_by("sort_order", "id"):
        RentalLine.objects.create(
            order=order,
            quote_line=source,
            line_type=source.line_type,
            description=source.description,
            equipment_model=source.equipment_model,
            asset=source.asset,
            rate_plan=source.rate_plan,
            quantity=source.quantity,
            start_at=source.start_at,
            end_at=source.end_at,
            pricing_unit=source.pricing_unit,
            unit_price=source.unit_price,
            discount_amount=source.discount_amount,
            line_total=source.line_total,
            tax_amount=source.tax_amount,
            price_snapshot=source.price_snapshot,
            sort_order=source.sort_order,
        )
    quote.status = Quote.Status.CONVERTED
    quote.save(update_fields=["status", "updated_at"])
    record_audit(
        "rental_order.created_from_quote",
        actor=actor,
        obj=order,
        quote_id=quote.pk,
    )
    return order


def release_expired_holds(*, asset=None):
    queryset = ReservationAllocation.objects.filter(
        status=ReservationAllocation.Status.HELD,
        hold_expires_at__lte=timezone.now(),
    )
    if asset is not None:
        queryset = queryset.filter(asset=asset)
    return queryset.update(status=ReservationAllocation.Status.RELEASED)


def has_allocation_conflict(asset, start_at, end_at, *, exclude_pk=None):
    release_expired_holds(asset=asset)
    queryset = ReservationAllocation.objects.filter(
        asset=asset,
        status__in=ACTIVE_ALLOCATION_STATUSES,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.exists()


@transaction.atomic
def create_allocation(
    rental_line,
    *,
    asset,
    start_at,
    end_at,
    status=ReservationAllocation.Status.CONFIRMED,
    actor=None,
    hold_minutes=30,
    allow_current_use=False,
):
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    if (
        rental_line.equipment_model_id
        and rental_line.equipment_model_id != asset.model_id
    ):
        raise ValidationError({"asset": "Asset does not match the rental line model."})
    allowed_statuses = set(ALLOCATABLE_ASSET_STATUSES)
    if allow_current_use:
        allowed_statuses.update(
            {
                Asset.Status.IN_TRANSIT,
                Asset.Status.ON_SITE,
                Asset.Status.PAUSED,
                Asset.Status.PENDING_COLLECTION,
            }
        )
    if asset.status not in allowed_statuses:
        raise ValidationError(
            {
                "asset": f"Asset {asset.asset_number} is not allocatable ({asset.status})."
            }
        )
    if has_allocation_conflict(asset, start_at, end_at):
        raise ValidationError(
            {"asset": f"Asset {asset.asset_number} is unavailable for the period."}
        )
    hold_expires_at = (
        timezone.now() + timedelta(minutes=hold_minutes)
        if status == ReservationAllocation.Status.HELD
        else None
    )
    allocation = ReservationAllocation.objects.create(
        rental_line=rental_line,
        asset=asset,
        start_at=start_at,
        end_at=end_at,
        status=status,
        hold_expires_at=hold_expires_at,
        created_by=actor,
    )
    if asset.status == Asset.Status.AVAILABLE:
        asset.transition_to(
            Asset.Status.RESERVED,
            actor=actor,
            reason=f"Reserved for {rental_line.order.number}",
            source="rental",
        )
    return allocation


def available_assets(equipment_model, start_at, end_at):
    release_expired_holds()
    candidates = Asset.objects.filter(
        model=equipment_model,
        status__in=ALLOCATABLE_ASSET_STATUSES,
    ).order_by("asset_number")
    return [
        asset
        for asset in candidates
        if not has_allocation_conflict(asset, start_at, end_at)
    ]


@transaction.atomic
def confirm_order(order, *, actor):
    order = (
        RentalOrder.objects.select_for_update(of=("self",))
        .select_related("customer", "site")
        .get(pk=order.pk)
    )
    if order.status != RentalOrder.Status.DRAFT:
        raise ValidationError({"status": "Only draft orders can be confirmed."})
    equipment_lines = order.lines.select_related("equipment_model", "asset").filter(
        line_type=RentalLine.LineType.EQUIPMENT,
        start_at__isnull=False,
        end_at__isnull=False,
    )
    if not equipment_lines.exists():
        raise ValidationError({"lines": "Order requires at least one equipment line."})

    for line in equipment_lines:
        start_at = line.start_at - timedelta(minutes=order.prep_buffer_minutes)
        end_at = line.end_at + timedelta(minutes=order.return_buffer_minutes)
        if line.asset_id:
            asset = line.asset
        else:
            if line.equipment_model_id is None:
                raise ValidationError(
                    {"lines": "Equipment lines require an equipment model."}
                )
            candidates = available_assets(line.equipment_model, start_at, end_at)
            if not candidates:
                raise ValidationError(
                    {
                        "lines": (
                            f"No available asset for {line.equipment_model} "
                            f"between {start_at.isoformat()} and {end_at.isoformat()}."
                        )
                    }
                )
            asset = candidates[0]
            line.asset = asset
            line.save(update_fields=["asset", "updated_at"])
        create_allocation(
            line,
            asset=asset,
            start_at=start_at,
            end_at=end_at,
            status=ReservationAllocation.Status.CONFIRMED,
            actor=actor,
        )

    order.status = RentalOrder.Status.RESERVED
    order.confirmed_by = actor
    order.confirmed_at = timezone.now()
    order.save(update_fields=["status", "confirmed_by", "confirmed_at", "updated_at"])
    record_audit("rental_order.confirmed", actor=actor, obj=order)
    return order


@transaction.atomic
def dispatch_order(order, *, actor):
    order = RentalOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != RentalOrder.Status.RESERVED:
        raise ValidationError({"status": "Only reserved orders can be dispatched."})
    for allocation in ReservationAllocation.objects.filter(
        rental_line__order=order,
        status=ReservationAllocation.Status.CONFIRMED,
    ).select_related("asset"):
        if allocation.asset.status == Asset.Status.RESERVED:
            allocation.asset.transition_to(
                Asset.Status.READY_FOR_DISPATCH,
                actor=actor,
                reason=f"Prepared for dispatch on {order.number}",
                source="rental",
            )
        allocation.asset.transition_to(
            Asset.Status.IN_TRANSIT,
            actor=actor,
            reason=f"Dispatched on {order.number}",
            source="rental",
        )
    order.status = RentalOrder.Status.ACTIVE
    order.dispatched_at = timezone.now()
    order.save(update_fields=["status", "dispatched_at", "updated_at"])
    record_audit("rental_order.dispatched", actor=actor, obj=order)
    return order


@transaction.atomic
def complete_return(order, *, actor):
    order = RentalOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != RentalOrder.Status.ACTIVE:
        raise ValidationError({"status": "Only active orders can be returned."})
    for allocation in ReservationAllocation.objects.filter(
        rental_line__order=order,
        status=ReservationAllocation.Status.CONFIRMED,
    ).select_related("asset"):
        allocation.status = ReservationAllocation.Status.RELEASED
        allocation.save(update_fields=["status"])
        allocation.asset.transition_to(
            Asset.Status.RETURN_INSPECTION,
            actor=actor,
            reason=f"Returned from {order.number}",
            source="rental",
        )
    order.status = RentalOrder.Status.COMPLETED
    order.returned_at = timezone.now()
    order.save(update_fields=["status", "returned_at", "updated_at"])
    record_audit("rental_order.returned", actor=actor, obj=order)
    return order


@transaction.atomic
def cancel_order(order, *, actor, reason):
    order = RentalOrder.objects.select_for_update().get(pk=order.pk)
    if order.status not in {RentalOrder.Status.DRAFT, RentalOrder.Status.RESERVED}:
        raise ValidationError({"status": "Order cannot be cancelled."})
    for allocation in ReservationAllocation.objects.filter(
        rental_line__order=order,
        status__in=ACTIVE_ALLOCATION_STATUSES,
    ).select_related("asset"):
        allocation.status = ReservationAllocation.Status.RELEASED
        allocation.save(update_fields=["status"])
        if allocation.asset.status == Asset.Status.RESERVED:
            allocation.asset.transition_to(
                Asset.Status.AVAILABLE,
                actor=actor,
                reason=f"Cancelled {order.number}",
                source="rental",
            )
    order.status = RentalOrder.Status.CANCELLED
    order.cancelled_reason = reason
    order.save(update_fields=["status", "cancelled_reason", "updated_at"])
    record_audit("rental_order.cancelled", actor=actor, obj=order, reason=reason)
    return order


@transaction.atomic
def renew_order(
    order,
    *,
    actor,
    start_at,
    end_at,
    asset,
    unit_price=None,
    description="Rental renewal",
):
    order = RentalOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != RentalOrder.Status.ACTIVE:
        raise ValidationError({"status": "Only active orders can be renewed."})
    if start_at < order.end_at:
        raise ValidationError(
            {"start_at": "Renewal cannot overlap the existing order."}
        )
    source_line = (
        order.lines.select_related("rate_plan", "equipment_model")
        .filter(asset=asset, line_type=RentalLine.LineType.EQUIPMENT)
        .first()
    )
    if source_line is None:
        raise ValidationError({"asset": "Asset is not part of this order."})
    line = RentalLine(
        order=order,
        line_type=RentalLine.LineType.EQUIPMENT,
        description=description,
        equipment_model=asset.model,
        asset=asset,
        rate_plan=source_line.rate_plan,
        quantity=Decimal("1"),
        start_at=start_at,
        end_at=end_at,
        pricing_unit=source_line.pricing_unit,
        unit_price=unit_price if unit_price is not None else source_line.unit_price,
        sort_order=order.lines.count(),
    )
    result = calculate_line(line)
    line.quantity = Decimal(result["quantity"])
    line.unit_price = result["unit_price"]
    line.line_total = result["total"]
    line.tax_amount = result["tax"]
    line.price_snapshot = result
    line.save()
    create_allocation(
        line,
        asset=asset,
        start_at=start_at - timedelta(minutes=order.prep_buffer_minutes),
        end_at=end_at + timedelta(minutes=order.return_buffer_minutes),
        actor=actor,
        allow_current_use=True,
    )
    order.end_at = max(order.end_at, end_at)
    order.subtotal += Decimal(result["subtotal"])
    order.discount_total += Decimal(result["discount"])
    order.tax_total += Decimal(result["tax"])
    order.total += Decimal(result["total"])
    order.deposit_total += Decimal(result["deposit"])
    order.price_snapshot = copy.deepcopy(order.price_snapshot)
    order.price_snapshot.setdefault("renewals", []).append(
        json_safe(
            {
                "line_id": line.pk,
                "asset_id": asset.pk,
                "start_at": start_at,
                "end_at": end_at,
                "total": str(result["total"]),
                "pricing": result,
            }
        )
    )
    order.save()
    record_audit(
        "rental_order.renewed",
        actor=actor,
        obj=order,
        line_id=line.pk,
        asset_id=asset.pk,
        total=str(result["total"]),
    )
    return order


def _contract_snapshot(order, contract, *, signed_by_name=""):
    return json_safe(
        {
            "contract_id": contract.pk,
            "order_number": order.number,
            "customer": {
                "id": order.customer_id,
                "name": order.customer.name,
                "legal_name": order.customer.legal_name,
                "billing_address": order.customer.billing_address,
            },
            "site": (
                {
                    "id": order.site_id,
                    "name": order.site.name,
                    "address": order.site.address,
                }
                if order.site_id
                else None
            ),
            "start_at": order.start_at,
            "end_at": order.end_at,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "discount_total": str(order.discount_total),
            "tax_total": str(order.tax_total),
            "total": str(order.total),
            "deposit_total": str(order.deposit_total),
            "lines": [
                {
                    "id": line.pk,
                    "asset_id": line.asset_id,
                    "asset_number": line.asset.asset_number if line.asset_id else None,
                    "description": line.description,
                    "start_at": line.start_at,
                    "end_at": line.end_at,
                    "line_total": str(line.line_total),
                    "pricing": line.price_snapshot,
                }
                for line in order.lines.select_related("asset").order_by(
                    "sort_order", "id"
                )
            ],
            "signed_by_name": signed_by_name,
        }
    )


@transaction.atomic
def issue_contract(order, *, actor):
    order = (
        RentalOrder.objects.select_for_update(of=("self",))
        .select_related("customer", "site")
        .get(pk=order.pk)
    )
    if order.status not in {RentalOrder.Status.RESERVED, RentalOrder.Status.ACTIVE}:
        raise ValidationError(
            {"status": "Contracts require a reserved or active order."}
        )
    contract, _ = Contract.objects.select_for_update().get_or_create(order=order)
    if contract.status == Contract.Status.SIGNED:
        raise ValidationError({"contract": "A signed contract cannot be replaced."})
    version_number = contract.current_version + 1
    snapshot = _contract_snapshot(order, contract)
    ContractVersion.objects.create(
        contract=contract,
        version=version_number,
        snapshot=snapshot,
        content_sha256=ContractVersion.hash_snapshot(snapshot),
        created_by=actor,
    )
    contract.status = Contract.Status.ISSUED
    contract.current_version = version_number
    contract.issued_at = timezone.now()
    contract.save(
        update_fields=["status", "current_version", "issued_at", "updated_at"]
    )
    record_audit(
        "contract.issued",
        actor=actor,
        obj=contract,
        version=version_number,
    )
    return contract


@transaction.atomic
def sign_contract(contract, *, actor, signed_by_name):
    contract = (
        Contract.objects.select_for_update(of=("self",))
        .select_related("order__customer", "order__site")
        .get(pk=contract.pk)
    )
    if contract.status != Contract.Status.ISSUED:
        raise ValidationError({"status": "Only issued contracts can be signed."})
    version_number = contract.current_version + 1
    snapshot = _contract_snapshot(
        contract.order, contract, signed_by_name=signed_by_name
    )
    ContractVersion.objects.create(
        contract=contract,
        version=version_number,
        snapshot=snapshot,
        content_sha256=ContractVersion.hash_snapshot(snapshot),
        created_by=actor,
    )
    contract.status = Contract.Status.SIGNED
    contract.current_version = version_number
    contract.signed_at = timezone.now()
    contract.signed_by_name = signed_by_name
    contract.save(
        update_fields=[
            "status",
            "current_version",
            "signed_at",
            "signed_by_name",
            "updated_at",
        ]
    )
    record_audit(
        "contract.signed",
        actor=actor,
        obj=contract,
        version=version_number,
        signed_by_name=signed_by_name,
    )
    return contract
