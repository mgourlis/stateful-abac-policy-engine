"""add external_id to realm_resource

Revision ID: fea3f9cbc372
Revises: 374dcd9107e4
Create Date: 2025-12-17 00:27:54.123456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fea3f9cbc372'
down_revision: Union[str, Sequence[str], None] = '374dcd9107e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('realm_resource', sa.Column('external_id', sa.String(), nullable=True))
    op.create_unique_constraint('uq_resource_type_external_id', 'realm_resource', ['resource_type_id', 'external_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_resource_type_external_id', 'realm_resource', type_='unique')
    op.drop_column('realm_resource', 'external_id')
