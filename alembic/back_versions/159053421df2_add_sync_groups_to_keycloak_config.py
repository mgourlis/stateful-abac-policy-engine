"""add_sync_groups_to_keycloak_config

Revision ID: 159053421df2
Revises: 49ac7dc8a1d3
Create Date: 2025-12-17 18:23:30.033711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '159053421df2'
down_revision: Union[str, Sequence[str], None] = '49ac7dc8a1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('realm_keycloak_config', sa.Column('sync_groups', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('realm_keycloak_config', 'sync_groups')
