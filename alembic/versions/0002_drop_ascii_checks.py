"""drop legacy ascii-only check constraints

Revision ID: 0002_drop_ascii_checks
Revises: 0001_initial
Create Date: 2025-09-03 21:30:00

This migration removes leftover CHECK constraints that were added by a previous
now-removed revision. It is intended for test/dev environments to make the DB
permissive and avoid spurious 4xx/5xx due to overly strict ASCII checks.

The script is idempotent: it only drops constraints whose names end with
"_ascii" in the public schema. If none exist, it does nothing.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_drop_ascii_checks"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Drop all CHECK constraints in public schema whose names end with _ascii
    # Use dynamic SQL via DO block for portability.
    conn.execute(
        sa.text(
            """
            DO $$
            DECLARE r RECORD;
            BEGIN
              FOR r IN 
                SELECT conrelid::regclass AS tbl, conname
                FROM pg_constraint
                WHERE contype='c' 
                  AND conrelid::regclass::text LIKE 'public.%'
                  AND conname LIKE '%_ascii'
              LOOP
                EXECUTE format('ALTER TABLE %s DROP CONSTRAINT IF EXISTS %I', r.tbl, r.conname);
              END LOOP;
            END$$;
            """
        )
    )


def downgrade() -> None:
    # We cannot reliably recreate unknown original CHECK constraints.
    # No-op downgrade.
    pass
