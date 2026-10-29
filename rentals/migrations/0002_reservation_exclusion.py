from django.db import migrations


POSTGRES_FORWARD = [
    "CREATE EXTENSION IF NOT EXISTS btree_gist",
    """
    ALTER TABLE rentals_reservationallocation
    ADD CONSTRAINT exclusion_reservation_asset_period
    EXCLUDE USING gist (
        asset_id WITH =,
        tstzrange(start_at, end_at, '[)') WITH &&
    )
    WHERE (status IN ('held', 'confirmed'))
    """,
]

POSTGRES_REVERSE = [
    """
    ALTER TABLE rentals_reservationallocation
    DROP CONSTRAINT IF EXISTS exclusion_reservation_asset_period
    """,
]

SQLITE_FORWARD = [
    """
    CREATE TRIGGER rentals_reservation_no_overlap_insert
    BEFORE INSERT ON rentals_reservationallocation
    WHEN NEW.status IN ('held', 'confirmed')
      AND EXISTS (
        SELECT 1
        FROM rentals_reservationallocation AS other
        WHERE other.asset_id = NEW.asset_id
          AND other.status IN ('held', 'confirmed')
          AND other.start_at < NEW.end_at
          AND other.end_at > NEW.start_at
      )
    BEGIN
        SELECT RAISE(ABORT, 'reservation allocation overlaps');
    END
    """,
    """
    CREATE TRIGGER rentals_reservation_no_overlap_update
    BEFORE UPDATE ON rentals_reservationallocation
    WHEN NEW.status IN ('held', 'confirmed')
      AND EXISTS (
        SELECT 1
        FROM rentals_reservationallocation AS other
        WHERE other.asset_id = NEW.asset_id
          AND other.id <> NEW.id
          AND other.status IN ('held', 'confirmed')
          AND other.start_at < NEW.end_at
          AND other.end_at > NEW.start_at
      )
    BEGIN
        SELECT RAISE(ABORT, 'reservation allocation overlaps');
    END
    """,
]

SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS rentals_reservation_no_overlap_insert",
    "DROP TRIGGER IF EXISTS rentals_reservation_no_overlap_update",
]


def add_constraints(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    statements = {
        "postgresql": POSTGRES_FORWARD,
        "sqlite": SQLITE_FORWARD,
    }.get(vendor)
    if statements:
        for statement in statements:
            schema_editor.execute(statement)


def remove_constraints(apps, schema_editor):
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
        ("rentals", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_constraints, remove_constraints),
    ]
