"""add_realm_keycloak_config

Revision ID: e8f9a6c4d2b1
Revises: 69bf31d48969
Create Date: 2025-12-16 23:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e8f9a6c4d2b1'
down_revision: Union[str, Sequence[str], None] = '69bf31d48969'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'realm_keycloak_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('server_url', sa.String(), nullable=False),
        sa.Column('keycloak_realm', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('client_secret', sa.String(), nullable=True),
        sa.Column('verify_ssl', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sync_cron', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', name='uq_realm_keycloak_realm_id')
    )


def downgrade() -> None:
    op.drop_table('realm_keycloak_config')

