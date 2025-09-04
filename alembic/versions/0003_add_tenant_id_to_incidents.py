"""add tenant_id to incidents

Revision ID: 0003_add_tenant_id_to_incidents
Revises: 0002_drop_ascii_checks
Create Date: 2025-09-04 13:05:00

"""
from alembic import op
import sqlalchemy as sa
import uuid

# revision identifiers, used by Alembic.
revision = '0003_add_tenant_id_to_incidents'
down_revision = '0002_drop_ascii_checks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column('incidents', sa.Column('tenant_id', sa.String(length=36), nullable=True))
    op.create_index('ix_incidents_tenant_id', 'incidents', ['tenant_id'])

    # Backfill existing rows with a random UUID per row
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT id FROM incidents WHERE tenant_id IS NULL"))
    ids = [row[0] for row in res]
    for iid in ids:
        conn.execute(sa.text("UPDATE incidents SET tenant_id = :tid WHERE id = :iid"), {
            'tid': str(uuid.uuid4()),
            'iid': iid,
        })

    # Set NOT NULL
    op.alter_column('incidents', 'tenant_id', existing_type=sa.String(length=36), nullable=False)


def downgrade() -> None:
    op.drop_index('ix_incidents_tenant_id', table_name='incidents')
    op.drop_column('incidents', 'tenant_id')
