import tempfile

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from core.cache import TenantScopedCache
from core.context import TenantContextMissing, get_current_tenant, tenant_context
from core.exports import tenant_csv_response
from core.jobs import TenantJobUnavailable, run_tenant_job
from core.models import AuditEvent, TenantMismatch, record_audit
from core.storage import TenantFileSystemStorage, TenantS3Storage
from tenants.models import Plan, Tenant
from tests_support.models import Widget


def make_tenant(slug, **kwargs):
    plan = kwargs.pop(
        "plan",
        Plan.objects.get_or_create(code="standard", defaults={"name": "Standard"})[0],
    )
    return Tenant.objects.create(slug=slug, name=slug.title(), plan=plan, **kwargs)


class BulkTenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_tenant("bulk-a")
        cls.b = make_tenant("bulk-b")

    def test_bulk_create_assigns_active_tenant(self):
        with tenant_context(self.a):
            Widget.objects.bulk_create([Widget(name="new-a")])
        widget = Widget.all_tenants.get(name="new-a")
        self.assertEqual(widget.tenant_id, self.a.pk)

    def test_bulk_create_rejects_another_tenant(self):
        with tenant_context(self.a):
            with self.assertRaises(TenantMismatch):
                Widget.objects.bulk_create([Widget(name="bad", tenant=self.b)])

    def test_bulk_operations_cannot_reassign_ownership(self):
        with tenant_context(self.a):
            widget = Widget.objects.create(name="owned-a")
            for operation in (
                lambda: Widget.objects.filter(pk=widget.pk).update(tenant=self.b),
                lambda: Widget.objects.bulk_update([widget], fields=["tenant"]),
            ):
                with self.assertRaises(TenantMismatch):
                    operation()


class CacheIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_tenant("cache-a")
        cls.b = make_tenant("cache-b")

    def setUp(self):
        caches["default"].clear()
        self.cache = TenantScopedCache()

    def tearDown(self):
        caches["default"].clear()

    def test_same_key_is_isolated_by_tenant(self):
        with tenant_context(self.a):
            self.cache.set("dashboard", {"tenant": "a"})
        with tenant_context(self.b):
            self.assertIsNone(self.cache.get("dashboard"))
            self.cache.set("dashboard", {"tenant": "b"})
        with tenant_context(self.a):
            self.assertEqual(self.cache.get("dashboard"), {"tenant": "a"})

    def test_cache_fails_closed_without_tenant(self):
        with self.assertRaises(TenantContextMissing):
            self.cache.get("dashboard")


class FileStorageIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_tenant("file-a")
        cls.b = make_tenant("file-b")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = TenantFileSystemStorage(
            location=self.temp_dir.name, base_url="/media/"
        )

    def test_same_file_name_is_physically_isolated(self):
        with tenant_context(self.a):
            saved_a = self.storage.save(
                "documents/report.txt", ContentFile(b"tenant-a")
            )
            path_a = self.storage.path(saved_a)
        with tenant_context(self.b):
            saved_b = self.storage.save(
                "documents/report.txt", ContentFile(b"tenant-b")
            )
            path_b = self.storage.path(saved_b)

        self.assertNotEqual(path_a, path_b)
        self.assertIn(f"tenants/{self.a.pk}/", path_a)
        self.assertIn(f"tenants/{self.b.pk}/", path_b)
        with tenant_context(self.a), self.storage.open(saved_a) as file_a:
            self.assertEqual(file_a.read(), b"tenant-a")

    def test_storage_fails_closed_without_tenant(self):
        with self.assertRaises(TenantContextMissing):
            self.storage.save("report.txt", ContentFile(b"no-tenant"))

    def test_s3_keys_are_tenant_prefixed(self):
        storage = TenantS3Storage(bucket_name="test-bucket")
        with tenant_context(self.a):
            key = storage._normalize_name("documents/report.txt")
        self.assertEqual(key, f"tenants/{self.a.pk}/documents/report.txt")


class BackgroundJobIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_tenant("job-a")
        cls.b = make_tenant("job-b")
        with tenant_context(cls.a):
            Widget.objects.create(name="from-a")
        with tenant_context(cls.b):
            Widget.objects.create(name="from-b")

    def test_job_runs_in_requested_tenant_and_clears_context(self):
        result = run_tenant_job(
            self.b.pk, lambda: list(Widget.objects.values_list("name", flat=True))
        )
        self.assertEqual(result, ["from-b"])
        self.assertIsNone(get_current_tenant())

    def test_suspended_tenant_cannot_run_job(self):
        Tenant.objects.filter(pk=self.a.pk).update(status=Tenant.Status.SUSPENDED)
        with self.assertRaises(TenantJobUnavailable):
            run_tenant_job(self.a.pk, lambda: None)


class CsvExportIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_tenant("export-a")
        cls.b = make_tenant("export-b")
        with tenant_context(cls.a):
            Widget.objects.create(name="export-a-widget")
        with tenant_context(cls.b):
            Widget.objects.create(name="export-b-widget")

    def test_export_filters_even_an_all_tenant_queryset(self):
        with tenant_context(self.a):
            response = tenant_csv_response(
                model=Widget,
                columns=[("Name", "name")],
                filename="widgets.csv",
                queryset=Widget.all_tenants.all(),
            )
            body = b"".join(response.streaming_content).decode()

        self.assertIn("export-a-widget", body)
        self.assertNotIn("export-b-widget", body)
        self.assertIn("export-a-widgets.csv", response["Content-Disposition"])
        self.assertTrue(
            AuditEvent.objects.filter(tenant=self.a, action="export.created").exists()
        )

    def test_export_rejects_non_scoped_models(self):
        with tenant_context(self.a):
            with self.assertRaises(TypeError):
                tenant_csv_response(
                    model=Tenant,
                    columns=[("Name", "name")],
                    filename="tenants.csv",
                )

    def test_export_neutralizes_spreadsheet_formulas(self):
        with tenant_context(self.a):
            Widget.objects.create(name='=HYPERLINK("https://example.invalid")')
            response = tenant_csv_response(
                model=Widget,
                columns=[("Name", "name")],
                filename="formula.csv",
            )
            body = b"".join(response.streaming_content).decode()
        self.assertIn("'=HYPERLINK", body)


class AuditImmutabilityTests(TestCase):
    def test_queryset_cannot_update_or_delete_audit_events(self):
        tenant = make_tenant("audit-immutable")
        event = record_audit("security.test", tenant=tenant)
        with self.assertRaises(PermissionError):
            AuditEvent.objects.filter(pk=event.pk).update(action="changed")
        with self.assertRaises(PermissionError):
            AuditEvent.objects.filter(pk=event.pk).delete()

    def test_database_rejects_raw_audit_mutation(self):
        tenant = make_tenant("audit-database-guard")
        event = record_audit("security.database-guard", tenant=tenant)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE core_auditevent SET action = %s WHERE id = %s",
                        ["tampered", event.pk],
                    )


class PlanValidationTests(TestCase):
    def test_features_must_be_a_list_of_non_empty_strings(self):
        with self.assertRaises(ValidationError):
            Plan.objects.create(
                code="invalid", name="Invalid", features={"asset_import": True}
            )
