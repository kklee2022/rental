from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import record_audit
from core.sequences import next_document_number
from core.serialization import json_safe
from rentals.models import RentalOrder
from tenants.settings_service import get_number_prefix

from .models import CreditNote, Deposit, Invoice, InvoiceLine, Payment, Refund


def _invoice_snapshot(invoice):
    return json_safe(
        {
            "invoice_id": invoice.pk,
            "number": invoice.number,
            "order_id": invoice.order_id,
            "order_number": invoice.order.number,
            "invoice_type": invoice.invoice_type,
            "currency": invoice.currency,
            "subtotal": str(invoice.subtotal),
            "tax_total": str(invoice.tax_total),
            "total": str(invoice.total),
            "lines": [
                {
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                    "tax_amount": str(line.tax_amount),
                    "line_total": str(line.line_total),
                    "source_rental_line_id": line.rental_line_id,
                    "pricing": line.price_snapshot,
                }
                for line in invoice.lines.all()
            ],
        }
    )


@transaction.atomic
def create_invoice_from_order(
    order_id, *, actor, invoice_type=Invoice.Type.FINAL, due_days=30
):
    order = RentalOrder.objects.select_for_update().get(pk=order_id)
    if order.status in {RentalOrder.Status.DRAFT, RentalOrder.Status.CANCELLED}:
        raise ValidationError(
            {"order": "Draft or cancelled orders cannot be invoiced."}
        )
    if (
        invoice_type == Invoice.Type.FINAL
        and Invoice.objects.filter(order=order, invoice_type=Invoice.Type.FINAL)
        .exclude(status=Invoice.Status.VOID)
        .exists()
    ):
        raise ValidationError(
            {"order": "A non-void final invoice already exists for this order."}
        )

    lines = list(order.lines.all())
    if not lines:
        raise ValidationError({"order": "Order has no lines to invoice."})
    issue_date = timezone.localdate()
    invoice = Invoice.objects.create(
        number=next_document_number("invoice", get_number_prefix("invoice")),
        order=order,
        invoice_type=invoice_type,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=due_days),
        currency=order.currency,
        created_by=actor,
    )
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    total = Decimal("0")
    for index, rental_line in enumerate(lines):
        pre_tax = rental_line.line_total - rental_line.tax_amount
        subtotal += pre_tax
        tax_total += rental_line.tax_amount
        total += rental_line.line_total
        InvoiceLine.objects.create(
            invoice=invoice,
            rental_line=rental_line,
            description=rental_line.description,
            quantity=rental_line.quantity,
            unit_price=rental_line.unit_price or 0,
            tax_amount=rental_line.tax_amount,
            line_total=rental_line.line_total,
            price_snapshot=rental_line.price_snapshot,
            sort_order=index,
        )
    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.total = total
    invoice.balance = total
    invoice.price_snapshot = _invoice_snapshot(invoice)
    invoice.save()
    record_audit(
        "invoice.created",
        actor=actor,
        obj=invoice,
        order_id=order.pk,
        total=str(total),
    )
    return invoice


@transaction.atomic
def issue_invoice(invoice, *, actor):
    invoice = (
        Invoice.objects.select_for_update(of=("self",))
        .select_related("order")
        .get(pk=invoice.pk)
    )
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"status": "Only draft invoices can be issued."})
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_by = actor
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["status", "issued_by", "issued_at", "updated_at"])
    record_audit("invoice.issued", actor=actor, obj=invoice)
    return invoice


def refresh_invoice_settlement(invoice):
    payments = Payment.objects.filter(invoice=invoice, status=Payment.Status.COMPLETED)
    payment_total = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    refund_total = Refund.objects.filter(
        payment__invoice=invoice,
        status=Refund.Status.COMPLETED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    credit_total = CreditNote.objects.filter(
        invoice=invoice, status=CreditNote.Status.ISSUED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    amount_paid = max(Decimal("0"), payment_total - refund_total)
    balance = max(Decimal("0"), invoice.total - credit_total - amount_paid)
    invoice.amount_paid = amount_paid
    invoice.credit_total = credit_total
    invoice.balance = balance
    if invoice.status != Invoice.Status.VOID:
        if balance == 0:
            invoice.status = Invoice.Status.PAID
        elif amount_paid > 0 or credit_total > 0:
            invoice.status = Invoice.Status.PARTIALLY_PAID
        else:
            invoice.status = Invoice.Status.ISSUED
    invoice.save(
        update_fields=[
            "amount_paid",
            "credit_total",
            "balance",
            "status",
            "updated_at",
        ]
    )
    return invoice


@transaction.atomic
def record_payment(
    invoice,
    *,
    actor,
    amount,
    method,
    received_at=None,
    reference="",
):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status not in {
        Invoice.Status.ISSUED,
        Invoice.Status.PARTIALLY_PAID,
    }:
        raise ValidationError({"invoice": "Invoice is not open for payment."})
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Payment amount must be positive."})
    if amount > invoice.balance:
        raise ValidationError({"amount": "Payment exceeds the invoice balance."})
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        received_at=received_at or timezone.now(),
        reference=reference,
        created_by=actor,
    )
    refresh_invoice_settlement(invoice)
    record_audit(
        "payment.recorded",
        actor=actor,
        obj=payment,
        invoice_id=invoice.pk,
        amount=str(amount),
    )
    return payment


@transaction.atomic
def record_refund(payment, *, actor, amount, reason):
    payment = (
        Payment.objects.select_for_update().select_related("invoice").get(pk=payment.pk)
    )
    if payment.status == Payment.Status.VOID:
        raise ValidationError({"payment": "Void payments cannot be refunded."})
    amount = Decimal(amount)
    refunded = payment.refunds.filter(status=Refund.Status.COMPLETED).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    if amount <= 0 or amount > payment.amount - refunded:
        raise ValidationError({"amount": "Refund exceeds the refundable amount."})
    refund = Refund.objects.create(
        payment=payment,
        amount=amount,
        reason=reason,
        processed_by=actor,
        processed_at=timezone.now(),
    )
    if refunded + amount == payment.amount:
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status"])
    refresh_invoice_settlement(payment.invoice)
    record_audit(
        "refund.recorded",
        actor=actor,
        obj=refund,
        payment_id=payment.pk,
        amount=str(amount),
    )
    return refund


@transaction.atomic
def issue_credit_note(invoice, *, actor, amount, tax_amount=0, reason=""):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status in {Invoice.Status.DRAFT, Invoice.Status.VOID}:
        raise ValidationError({"invoice": "Invoice is not open for credit."})
    amount = Decimal(amount)
    credit_available = invoice.total - invoice.credit_total
    if amount <= 0 or amount > credit_available:
        raise ValidationError({"amount": "Credit note exceeds the creditable amount."})
    note = CreditNote.objects.create(
        number=next_document_number("credit_note", "CN"),
        invoice=invoice,
        amount=amount,
        tax_amount=Decimal(tax_amount),
        reason=reason,
        issued_by=actor,
        issued_at=timezone.now(),
        snapshot=json_safe(
            {
                "invoice_number": invoice.number,
                "amount": str(amount),
                "tax_amount": str(tax_amount),
                "reason": reason,
            }
        ),
    )
    refresh_invoice_settlement(invoice)
    record_audit(
        "credit_note.issued",
        actor=actor,
        obj=note,
        invoice_id=invoice.pk,
        amount=str(amount),
    )
    return note


@transaction.atomic
def void_invoice(invoice, *, actor, reason):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.amount_paid or invoice.credit_total:
        raise ValidationError(
            {"status": "Invoices with payments or credits cannot be voided."}
        )
    invoice.status = Invoice.Status.VOID
    invoice.save(update_fields=["status", "updated_at"])
    record_audit("invoice.voided", actor=actor, obj=invoice, reason=reason)
    return invoice


@transaction.atomic
def record_deposit(order_id, *, actor, amount, received_at=None, note=""):
    order = RentalOrder.objects.get(pk=order_id)
    if order.status == RentalOrder.Status.CANCELLED:
        raise ValidationError({"order": "Cancelled orders cannot receive deposits."})
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Deposit must be positive."})
    deposit = Deposit.objects.create(
        order=order,
        amount=amount,
        received_at=received_at or timezone.now(),
        note=note,
        created_by=actor,
    )
    record_audit(
        "deposit.recorded",
        actor=actor,
        obj=deposit,
        order_id=order.pk,
        amount=str(amount),
    )
    return deposit


@transaction.atomic
def apply_deposit(deposit, *, actor, invoice):
    deposit = Deposit.objects.select_for_update().get(pk=deposit.pk)
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if deposit.status != Deposit.Status.HELD:
        raise ValidationError({"deposit": "Only held deposits can be applied."})
    if invoice.status not in {
        Invoice.Status.ISSUED,
        Invoice.Status.PARTIALLY_PAID,
    }:
        raise ValidationError({"invoice": "Invoice is not open for payment."})
    if deposit.amount > invoice.balance:
        raise ValidationError({"deposit": "Deposit exceeds the invoice balance."})
    Payment.objects.create(
        invoice=invoice,
        amount=deposit.amount,
        method=Payment.Method.DEPOSIT,
        reference=f"Deposit {deposit.pk}",
        received_at=timezone.now(),
        created_by=actor,
    )
    deposit.status = Deposit.Status.APPLIED
    deposit.applied_to_invoice = invoice
    deposit.save(update_fields=["status", "applied_to_invoice"])
    refresh_invoice_settlement(invoice)
    record_audit(
        "deposit.applied",
        actor=actor,
        obj=deposit,
        invoice_id=invoice.pk,
    )
    return deposit


@transaction.atomic
def refund_deposit(deposit, *, actor, reason=""):
    deposit = Deposit.objects.select_for_update().get(pk=deposit.pk)
    if deposit.status != Deposit.Status.HELD:
        raise ValidationError({"deposit": "Only held deposits can be refunded."})
    deposit.status = Deposit.Status.REFUNDED
    deposit.note = f"{deposit.note}\nRefund: {reason}".strip()
    deposit.save(update_fields=["status", "note"])
    record_audit(
        "deposit.refunded",
        actor=actor,
        obj=deposit,
        amount=str(deposit.amount),
        reason=reason,
    )
    return deposit
