"""initial_tables

Revision ID: 8d653be14d29
Revises: 
Create Date: 2025-12-16 17:36:11.696125

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8d653be14d29'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. realm
    op.create_table(
        'realm',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # 2. resource_type
    op.create_table(
        'resource_type',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', 'name')
    )

    # 3. action
    op.create_table(
        'action',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', 'name')
    )

    # 4. principal
    op.create_table(
        'principal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    # Index attributes using GIN
    op.create_index('ix_principal_attributes', 'principal', ['attributes'], unique=False, postgresql_using='gin')

    # 5. auth_role
    op.create_table(
        'auth_role',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. principal_roles
    op.create_table(
        'principal_roles',
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['principal_id'], ['principal.id'], ),
        sa.ForeignKeyConstraint(['role_id'], ['auth_role.id'], ),
        sa.PrimaryKeyConstraint('principal_id', 'role_id')
    )


def downgrade() -> None:
    op.drop_table('principal_roles')
    op.drop_table('auth_role')
    op.drop_index('ix_principal_attributes', table_name='principal', postgresql_using='gin')
    op.drop_table('principal')
    op.drop_table('action')
    op.drop_table('resource_type')
    op.drop_table('realm')
