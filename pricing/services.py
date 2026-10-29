import math
from decimal import Decimal, ROUND_HALF_UP

from .models import RatePlan

MONEY = Decimal("0.01")


def money(value):
    return Decimal(value or 0).quantize(MONEY, rounding=ROUND_HALF_UP)


def _duration_units(start_at, end_at, pricing_unit):
    if start_at is None or end_at is None or end_at <= start_at:
        return Decimal("1")
    seconds = Decimal(str((end_at - start_at).total_seconds()))
    divisors = {
        RatePlan.TimeUnit.HOUR: Decimal("3600"),
        RatePlan.TimeUnit.DAY: Decimal("86400"),
        RatePlan.TimeUnit.WEEK: Decimal("604800"),
        RatePlan.TimeUnit.MONTH: Decimal("2592000"),
    }
    divisor = divisors.get(pricing_unit)
    if divisor is None:
        return Decimal("1")
    return Decimal(max(1, math.ceil(seconds / divisor)))


def calculate_line(line):
    """Calculate a quote/rental line and return a reproducible snapshot."""

    plan = line.rate_plan
    pricing_unit = line.pricing_unit or (
        plan.time_unit if plan is not None else RatePlan.TimeUnit.FIXED
    )
    quantity = _duration_units(line.start_at, line.end_at, pricing_unit)
    if pricing_unit not in {
        RatePlan.TimeUnit.HOUR,
        RatePlan.TimeUnit.DAY,
        RatePlan.TimeUnit.WEEK,
        RatePlan.TimeUnit.MONTH,
    }:
        quantity = Decimal(line.quantity or 0)

    default_unit_price = plan.base_unit_price if plan is not None else Decimal("0")
    unit_price = line.unit_price if line.unit_price is not None else default_unit_price
    base_amount = money(quantity * unit_price)
    if plan is not None and base_amount < plan.minimum_charge:
        base_amount = money(plan.minimum_charge)

    items = [
        {
            "code": "base_rental",
            "name": "Base rental",
            "component_type": "time",
            "pricing_method": "per_unit",
            "quantity": str(quantity),
            "unit_price": str(money(unit_price)),
            "amount": str(base_amount),
            "taxable": True,
        }
    ]

    components_total = Decimal("0")
    if plan is not None:
        components = plan.components.all()
        if line.equipment_model_id:
            components = components.filter(
                equipment_model__in=[None, line.equipment_model_id]
            )
        else:
            components = components.filter(equipment_model__isnull=True)
        for component in components:
            if component.pricing_method == component.Method.FIXED:
                amount = component.unit_price
                component_quantity = Decimal("1")
            elif component.pricing_method == component.Method.PERCENTAGE:
                amount = base_amount * component.unit_price / Decimal("100")
                component_quantity = Decimal("1")
            else:
                component_quantity = max(
                    Decimal("0"), quantity - component.included_quantity
                )
                amount = component_quantity * component.unit_price
            amount = money(amount)
            if component.component_type == component.Type.DISCOUNT:
                amount = -abs(amount)
            components_total += amount
            items.append(
                {
                    "code": component.code,
                    "name": component.name,
                    "component_type": component.component_type,
                    "pricing_method": component.pricing_method,
                    "quantity": str(component_quantity),
                    "unit": component.unit,
                    "unit_price": str(money(component.unit_price)),
                    "amount": str(amount),
                    "taxable": component.taxable,
                }
            )

    gross = money(base_amount + components_total)
    discount = min(max(Decimal(line.discount_amount or 0), Decimal("0")), gross)
    taxable = max(Decimal("0"), gross - discount)
    tax_rate = plan.tax_rate if plan is not None else Decimal("0")
    tax = money(taxable * tax_rate / Decimal("100"))
    total = money(taxable + tax)
    deposit_percentage = plan.deposit_percentage if plan is not None else Decimal("0")
    deposit = money(taxable * deposit_percentage / Decimal("100"))

    return {
        "quantity": str(quantity),
        "unit_price": str(money(unit_price)),
        "subtotal": str(gross),
        "discount": str(money(discount)),
        "tax": str(tax),
        "total": str(total),
        "deposit": str(deposit),
        "currency": plan.currency if plan is not None else "HKD",
        "pricing_unit": pricing_unit,
        "items": items,
        "tax_rate": str(tax_rate),
        "source": {
            "rate_plan_id": plan.pk if plan is not None else None,
            "rate_plan_code": plan.code if plan is not None else None,
        },
    }
