"""Add auth performance indexes

Revision ID: 2_auth_indexes
Revises: 9d31f60a6f49
Create Date: 2025-12-20

Adds indexes for optimizing /check-access endpoint:
- external_ids lookups by (realm, type, external_id)
- external_ids reverse mapping by (realm, type, resource_id)
- acl matching by (realm, type, action)
"""
from typing import Sequence, Union
from alembic import op


revision: str = '2_auth_indexes'
down_revision: Union[str, Sequence[str], None] = '9d31f60a6f49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Index for external_id lookups (most frequent query)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_external_ids_lookup 
        ON external_ids (realm_id, resource_type_id, external_id)
    """)
    
    # Index for reverse mapping (internal -> external)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_external_ids_reverse 
        ON external_ids (realm_id, resource_type_id, resource_id)
    """)
    
    # Index for ACL matching - most common query pattern
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_acl_matching 
        ON acl (realm_id, resource_type_id, action_id)
    """)
    
    # Partial index for principal-based ACLs
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_acl_principal 
        ON acl (realm_id, resource_type_id, action_id, principal_id)
        WHERE principal_id != 0
    """)
    
    # Partial index for role-based ACLs  
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_acl_role 
        ON acl (realm_id, resource_type_id, action_id, role_id)
        WHERE role_id != 0
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_acl_role")
    op.execute("DROP INDEX IF EXISTS idx_acl_principal")
    op.execute("DROP INDEX IF EXISTS idx_acl_matching")
    op.execute("DROP INDEX IF EXISTS idx_external_ids_reverse")
    op.execute("DROP INDEX IF EXISTS idx_external_ids_lookup")
