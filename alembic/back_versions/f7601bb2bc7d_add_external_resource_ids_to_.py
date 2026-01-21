"""add_external_resource_ids_to_authorization_log

Revision ID: f7601bb2bc7d
Revises: b778fb01b0af
Create Date: 2025-12-17 12:44:45.825477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7601bb2bc7d'
down_revision: Union[str, Sequence[str], None] = 'b778fb01b0af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('authorization_log', sa.Column('external_resource_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('authorization_log', 'external_resource_ids')
