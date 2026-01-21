"""Add public_key and algorithm to RealmKeycloakConfig

Revision ID: 9d31f60a6f49
Revises: 1_init
Create Date: 2025-12-20 03:45:43.250527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9d31f60a6f49'
down_revision: Union[str, Sequence[str], None] = '1_init'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('realm_keycloak_config', sa.Column('public_key', sa.String(), nullable=True))
    op.add_column('realm_keycloak_config', sa.Column('algorithm', sa.String(), server_default='RS256', nullable=False))
    # We remove the default after creation if we don't want it enforced on the DB side, 
    # but server_default helps existing rows.
    # The model has default='RS256' but that's python side.
    # nullable=False means we likely want a default.


def downgrade() -> None:
    op.drop_column('realm_keycloak_config', 'algorithm')
    op.drop_column('realm_keycloak_config', 'public_key')
