"""fix_acl_check_constraint_for_pk

Revision ID: b778fb01b0af
Revises: 21668530a95d
Create Date: 2025-12-17 01:45:29.993387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b778fb01b0af'
down_revision: Union[str, Sequence[str], None] = '21668530a95d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE acl DROP CONSTRAINT IF EXISTS acl_check")
    # New check: Use 0 as 'None' because PK columns are NOT NULL
    op.execute("""
        ALTER TABLE acl ADD CONSTRAINT acl_check CHECK (
            (principal_id != 0 AND role_id = 0) OR
            (principal_id = 0 AND role_id != 0)
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE acl DROP CONSTRAINT IF EXISTS acl_check")
    # Restore old check
    op.execute("""
        ALTER TABLE acl ADD CONSTRAINT acl_check CHECK (
            (principal_id IS NOT NULL AND role_id IS NULL) OR
            (principal_id IS NULL AND role_id IS NOT NULL)
        )
    """)
