"""ascii-only constraints on text columns

Revision ID: 0002_english_only_constraints
Revises: 0001_initial
Create Date: 2025-08-27 14:20:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_english_only_constraints'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

# Regex for ASCII-only (0x00-0x7F). In Postgres, use ~ '^[\x00-\x7F]*$'
ASCII_ONLY = r"'^[\\x00-\\x7F]*$'"


def upgrade() -> None:
    # incidents
    op.create_check_constraint(
        constraint_name="ck_incidents_source_ascii",
        table_name="incidents",
        condition=f"source ~ {ASCII_ONLY}",
    )
    op.create_check_constraint(
        constraint_name="ck_incidents_status_ascii",
        table_name="incidents",
        condition=f"status ~ {ASCII_ONLY}",
    )
    op.create_check_constraint(
        constraint_name="ck_incidents_summary_ascii",
        table_name="incidents",
        condition=f"summary IS NULL OR summary ~ {ASCII_ONLY}",
    )

    # actions
    op.create_check_constraint(
        constraint_name="ck_actions_kind_ascii",
        table_name="actions",
        condition=f"kind ~ {ASCII_ONLY}",
    )

    # evidence
    op.create_check_constraint(
        constraint_name="ck_evidence_kind_ascii",
        table_name="evidence",
        condition=f"kind ~ {ASCII_ONLY}",
    )
    op.create_check_constraint(
        constraint_name="ck_evidence_path_ascii",
        table_name="evidence",
        condition=f"path ~ {ASCII_ONLY}",
    )
    op.create_check_constraint(
        constraint_name="ck_evidence_hash_ascii",
        table_name="evidence",
        condition=f"hash IS NULL OR hash ~ {ASCII_ONLY}",
    )

    # tickets
    op.create_check_constraint(
        constraint_name="ck_tickets_external_id_ascii",
        table_name="tickets",
        condition=f"external_id ~ {ASCII_ONLY}",
    )
    op.create_check_constraint(
        constraint_name="ck_tickets_system_ascii",
        table_name="tickets",
        condition=f"system ~ {ASCII_ONLY}",
    )
    op.create_check_constraint(
        constraint_name="ck_tickets_status_ascii",
        table_name="tickets",
        condition=f"status ~ {ASCII_ONLY}",
    )


def downgrade() -> None:
    # tickets
    op.drop_constraint("ck_tickets_status_ascii", table_name="tickets", type_="check")
    op.drop_constraint("ck_tickets_system_ascii", table_name="tickets", type_="check")
    op.drop_constraint("ck_tickets_external_id_ascii", table_name="tickets", type_="check")

    # evidence
    op.drop_constraint("ck_evidence_hash_ascii", table_name="evidence", type_="check")
    op.drop_constraint("ck_evidence_path_ascii", table_name="evidence", type_="check")
    op.drop_constraint("ck_evidence_kind_ascii", table_name="evidence", type_="check")

    # actions
    op.drop_constraint("ck_actions_kind_ascii", table_name="actions", type_="check")

    # incidents
    op.drop_constraint("ck_incidents_summary_ascii", table_name="incidents", type_="check")
    op.drop_constraint("ck_incidents_status_ascii", table_name="incidents", type_="check")
    op.drop_constraint("ck_incidents_source_ascii", table_name="incidents", type_="check")
