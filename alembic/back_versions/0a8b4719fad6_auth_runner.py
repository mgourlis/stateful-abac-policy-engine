"""auth_runner

Revision ID: 0a8b4719fad6
Revises: 446cd5ee7d19
Create Date: 2025-12-16 17:41:12.995932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a8b4719fad6'
down_revision: Union[str, Sequence[str], None] = '446cd5ee7d19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    print("APPLYING CLEAN AUTH RUNNER MIGRATION")
    op.execute("""
    CREATE OR REPLACE FUNCTION get_authorized_resources(
        p_realm_id INT,
        p_principal_id INT,
        p_action_id INT,
        p_resource_type_id INT,
        p_ctx JSONB
    )
    RETURNS TABLE (id INT) AS $$
    DECLARE
        v_sql TEXT;
        v_query TEXT;
    BEGIN
        -- Step 1: Find Compiled SQL
        -- Logic: Match realm, action, resource_type.
        -- Match principal_id OR role_id.
        -- Order by principal_id NULLS LAST (Specific overrides generic).
        -- LIMIT 1.
        -- Note: principal_id nulls last puts Non-Null (specific principal) first.
        SELECT compiled_sql INTO v_sql
        FROM acl
        WHERE realm_id = p_realm_id
          AND action_id = p_action_id
          AND resource_type_id = p_resource_type_id
          AND (principal_id = p_principal_id OR role_id IN (
              SELECT role_id FROM principal_roles WHERE principal_id = p_principal_id
          ))
        ORDER BY principal_id NULLS LAST
        LIMIT 1;

        -- Step 2: Handle Null
        -- If no rule found, default is DENY (return empty set)
        -- Or if v_sql is generated as NULL from NULL conditions? (Triggers set it to 'TRUE' if conditions null)
        -- So this check catches "No Row Found in ACL".
        IF v_sql IS NULL THEN
            RETURN;
        END IF;

        -- Step 3: Dynamic Execution
        -- Replace 'p_ctx' with '$3' to bind to p_ctx parameter
        v_sql := replace(v_sql, 'p_ctx', '$3');

        v_query := 'SELECT id FROM resource WHERE realm_id = $1 AND resource_type_id = $2 AND (' || v_sql || ')';
        
        RETURN QUERY EXECUTE v_query USING p_realm_id, p_resource_type_id, p_ctx;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_authorized_resources")
