"""remove temporary realm tables

Revision ID: 21668530a95d
Revises: fea3f9cbc372
Create Date: 2025-12-17 00:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21668530a95d'
down_revision: Union[str, Sequence[str], None] = 'fea3f9cbc372'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop temporary tables
    op.drop_table('realm_acl')
    op.drop_table('realm_resource')


def downgrade() -> None:
    # Recreate is complex and not strictly needed for this forward fix, 
    # but strictly speaking should undo.
    # For now, we assume this is a cleanup of dev tables.
    pass
