from django.db import migrations


POSTGRES_FORWARD = [
    """
CREATE OR REPLACE FUNCTION core_prevent_audit_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit events are append-only';
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER core_audit_event_append_only
BEFORE UPDATE OR DELETE ON core_auditevent
FOR EACH ROW EXECUTE FUNCTION core_prevent_audit_mutation();
""",
]

POSTGRES_REVERSE = [
    """
DROP TRIGGER IF EXISTS core_audit_event_append_only ON core_auditevent;
""",
    """
DROP FUNCTION IF EXISTS core_prevent_audit_mutation();
""",
]

SQLITE_FORWARD = [
    """
CREATE TRIGGER core_audit_event_no_update
BEFORE UPDATE ON core_auditevent
BEGIN
    SELECT RAISE(ABORT, 'audit events are append-only');
END;
""",
    """
CREATE TRIGGER core_audit_event_no_delete
BEFORE DELETE ON core_auditevent
BEGIN
    SELECT RAISE(ABORT, 'audit events cannot be deleted');
END;
""",
]

SQLITE_REVERSE = [
    """
DROP TRIGGER IF EXISTS core_audit_event_no_update;
""",
    """
DROP TRIGGER IF EXISTS core_audit_event_no_delete;
""",
]


def add_audit_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    statements = {
        "postgresql": POSTGRES_FORWARD,
        "sqlite": SQLITE_FORWARD,
    }.get(vendor)
    if statements:
        for statement in statements:
            schema_editor.execute(statement)


def remove_audit_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    statements = {
        "postgresql": POSTGRES_REVERSE,
        "sqlite": SQLITE_REVERSE,
    }.get(vendor)
    if statements:
        for statement in statements:
            schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_audit_guards, remove_audit_guards),
    ]
