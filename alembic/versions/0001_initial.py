"""initial tables

Revision ID: 0001_initial
Revises: 
Create Date: 2025-08-27 13:05:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # incidents
    op.create_table(
        'incidents',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
    )
    op.create_index('ix_incidents_created_at', 'incidents', ['created_at'])
    op.create_index('ix_incidents_status', 'incidents', ['status'])

    # actions
    op.create_table(
        'actions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('incident_id', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_actions_kind', 'actions', ['kind'])
    op.create_index('ix_actions_at', 'actions', ['at'])

    # evidence
    op.create_table(
        'evidence',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('incident_id', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('hash', sa.String(length=128), nullable=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_evidence_kind', 'evidence', ['kind'])
    op.create_index('ix_evidence_at', 'evidence', ['at'])

    # tickets
    op.create_table(
        'tickets',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('incident_id', sa.BigInteger(), nullable=False),
        sa.Column('external_id', sa.String(length=100), nullable=False),
        sa.Column('system', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_tickets_system', 'tickets', ['system'])
    op.create_index('ix_tickets_status', 'tickets', ['status'])
    op.create_index('ix_tickets_at', 'tickets', ['at'])


def downgrade() -> None:
    op.drop_index('ix_tickets_at', table_name='tickets')
    op.drop_index('ix_tickets_status', table_name='tickets')
    op.drop_index('ix_tickets_system', table_name='tickets')
    op.drop_table('tickets')

    op.drop_index('ix_evidence_at', table_name='evidence')
    op.drop_index('ix_evidence_kind', table_name='evidence')
    op.drop_table('evidence')

    op.drop_index('ix_actions_at', table_name='actions')
    op.drop_index('ix_actions_kind', table_name='actions')
    op.drop_table('actions')

    op.drop_index('ix_incidents_status', table_name='incidents')
    op.drop_index('ix_incidents_created_at', table_name='incidents')
    op.drop_table('incidents')
