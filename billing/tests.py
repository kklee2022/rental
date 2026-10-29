from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from billing.models import CreditNote, Deposit, Invoice, Payment
from billing.services import (
    apply_deposit,
    create_invoice_from_order,
    issue_credit_note,
    issue_invoice,
    record_deposit,
    record_payment,
    record_refund,
)
from core.context import tenant_context
from rentals.models import RentalLine, RentalOrder
from tests_support.factories import (
    make_asset,
    make_customer,
    make_equipment_model,
    make_owner,
    make_rate_plan,
    make_rental_period,
    make_site,
    make_tenant,
)


class BillingLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("billing")
        cls.other_tenant = make_tenant("billing-other")
        cls.owner = make_owner(cls.tenant, "billing-owner")
        cls.customer = make_customer(cls.tenant)
        cls.site = make_site(cls.tenant, cls.customer)
        cls.equipment_model = make_equipment_model(cls.tenant)
        cls.asset = make_asset(cls.tenant, cls.equipment_model, "BILLING-ASSET")
        cls.rate_plan = make_rate_plan(cls.tenant)
        start, end = make_rental_period()
        with tenant_context(cls.tenant):
            cls.order = RentalOrder.objects.create(
                number="ORDER-BILL-1",
                customer=cls.customer,
                site=cls.site,
                status=RentalOrder.Status.RESERVED,
                start_at=start,
                end_at=end,
                subtotal=Decimal("100"),
                tax_total=Decimal("10"),
                total=Decimal("110"),
                deposit_total=Decimal("20"),
                created_by=cls.owner,
            )
            RentalLine.objects.create(
                order=cls.order,
                line_type=RentalLine.LineType.EQUIPMENT,
                description="Billable excavator",
                equipment_model=cls.equipment_model,
                asset=cls.asset,
                rate_plan=cls.rate_plan,
                quantity=2,
                start_at=start,
                end_at=end,
                pricing_unit="day",
                unit_price=50,
                line_total=110,
                tax_amount=10,
            )

    def test_invoice_payment_refund_and_credit_note_flow(self):
        with tenant_context(self.tenant):
            invoice = create_invoice_from_order(
                self.order.pk, actor=self.owner, due_days=14
            )
            self.assertEqual(invoice.total, Decimal("110.00"))
            invoice = issue_invoice(invoice, actor=self.owner)
            first_payment = record_payment(
                invoice,
                actor=self.owner,
                amount=50,
                method=Payment.Method.BANK_TRANSFER,
                reference="BANK-1",
            )
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.PARTIALLY_PAID)
            self.assertEqual(invoice.balance, Decimal("60.00"))
            record_payment(
                invoice,
                actor=self.owner,
                amount=60,
                method=Payment.Method.FPS,
                reference="FPS-1",
            )
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.PAID)
            record_refund(
                first_payment,
                actor=self.owner,
                amount=20,
                reason="Operator cancelled",
            )
            invoice.refresh_from_db()
            self.assertEqual(invoice.balance, Decimal("20.00"))
            self.assertEqual(invoice.status, Invoice.Status.PARTIALLY_PAID)
            issue_credit_note(
                invoice,
                actor=self.owner,
                amount=20,
                reason="Service credit",
            )
            invoice.refresh_from_db()
            self.assertEqual(invoice.balance, Decimal("0.00"))
            self.assertEqual(invoice.status, Invoice.Status.PAID)
            self.assertTrue(
                CreditNote.objects.filter(
                    invoice=invoice, status=CreditNote.Status.ISSUED
                ).exists()
            )

    def test_duplicate_final_invoice_is_rejected(self):
        with tenant_context(self.tenant):
            create_invoice_from_order(self.order.pk, actor=self.owner)
            with self.assertRaises(ValidationError):
                create_invoice_from_order(self.order.pk, actor=self.owner)

    def test_deposit_can_be_applied_to_invoice(self):
        with tenant_context(self.tenant):
            deposit = record_deposit(
                self.order.pk, actor=self.owner, amount=20, note="Cash deposit"
            )
            invoice = create_invoice_from_order(self.order.pk, actor=self.owner)
            invoice = issue_invoice(invoice, actor=self.owner)
            deposit = apply_deposit(deposit, actor=self.owner, invoice=invoice)
            invoice.refresh_from_db()
        self.assertEqual(deposit.status, Deposit.Status.APPLIED)
        self.assertEqual(invoice.amount_paid, Decimal("20.00"))
        self.assertEqual(invoice.balance, Decimal("90.00"))

    def test_accounting_export_and_report(self):
        with tenant_context(self.tenant):
            invoice = create_invoice_from_order(self.order.pk, actor=self.owner)
            issue_invoice(invoice, actor=self.owner)

        self.client.force_login(self.owner)
        headers = {"HTTP_X_TENANT": self.tenant.slug}
        export = self.client.get("/api/v1/exports/accounting.csv", **headers)
        self.assertEqual(export.status_code, 200)
        body = b"".join(export.streaming_content).decode()
        self.assertIn(invoice.number, body)
        self.assertIn(self.order.number, body)

        report = self.client.get("/api/v1/reports/billing/", **headers)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(Decimal(str(report.json()["outstanding"])), Decimal("110.00"))

    def test_payment_api_records_payment(self):
        with tenant_context(self.tenant):
            invoice = create_invoice_from_order(self.order.pk, actor=self.owner)
            issue_invoice(invoice, actor=self.owner)
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/payments/record/",
            {
                "invoice_id": invoice.pk,
                "amount": "25.00",
                "method": "bank_transfer",
                "reference": "API-PAYMENT",
            },
            content_type="application/json",
            HTTP_X_TENANT=self.tenant.slug,
        )
        self.assertEqual(response.status_code, 201)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("25.00"))
