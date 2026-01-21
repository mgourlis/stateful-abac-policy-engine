"""audit_log

Revision ID: 2dd87038dfeb
Revises: 0a8b4719fad6
Create Date: 2025-12-16 17:42:12.995932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2dd87038dfeb'
down_revision: Union[str, Sequence[str], None] = '0a8b4719fad6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'authorization_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('action_name', sa.String(), nullable=True),
        sa.Column('resource_type_name', sa.String(), nullable=True),
        sa.Column('decision', sa.Boolean(), nullable=False),
        sa.Column('resource_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    # Using names instead of IDs for audit might be safer if IDs change or for readability, 
    # but the prompt assumes "log_authorization".
    # I'll stick to mostly names or IDs? 
    # The endpoint has names. Resolving to IDs is done. I have IDs.
    # IDs are better for relational integrity but logging often uses values.
    # I'll use IDs if I have them, but I added names too.
    # Actually, in the endpoint I have IDs.
    # I'll update columns to use names for easier reading without join, or IDs.
    # Standard practice: IDs.
    # But wait, `action_name` and `resource_type_name` were used in input.
    # I'll switch to IDs to match previous pattern, or keep names.
    # I'll stick to what I wrote: action_name, resource_type_name (snapshot).


def downgrade() -> None:
    op.drop_table('authorization_log')
