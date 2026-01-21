"""add_acl_gatekeeper_logic

Revision ID: d808a294638b
Revises: a1b2c3d4e5f6
Create Date: 2025-12-17 16:26:10.113438

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd808a294638b'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE FUNCTION get_authorized_resources(
        p_realm_id INT,
        p_principal_id INT,
        p_role_ids INT[], 
        p_resource_type_id INT,
        p_action_id INT,
        p_ctx JSONB
    )
    RETURNS TABLE(id INT) AS $$
    DECLARE
        v_acl_sql TEXT;
        v_final_sql TEXT;
        rec RECORD;
    BEGIN
        -- STANDARD UNION LOGIC
        -- Iterate all matching ACLs (Class or Specific) and accumulate results.
        -- No prioritization or blocking.
        FOR rec IN
            SELECT compiled_sql
            FROM acl
            WHERE realm_id = p_realm_id
              AND resource_type_id = p_resource_type_id
              AND action_id = p_action_id
              AND (
                  (principal_id = p_principal_id)
                  OR
                  (role_id = ANY(p_role_ids))
              )
        LOOP
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                v_final_sql := 'TRUE';
            ELSE
                v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            END IF;
            
            v_acl_sql := format(
                'SELECT id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
                p_realm_id,
                p_resource_type_id,
                v_final_sql
            );
            
            RETURN QUERY EXECUTE v_acl_sql USING p_ctx;
        END LOOP;
        RETURN;
    END;
    $$ LANGUAGE plpgsql;
    """)

def downgrade() -> None:
    """Downgrade schema (Revert to previous version without Gatekeeper)."""
    # Simply recreate without the PERFORM check (Same as 1305ecc80b4d or previous state)
    op.execute("""
    CREATE OR REPLACE FUNCTION get_authorized_resources(
        p_realm_id INT,
        p_principal_id INT,
        p_role_ids INT[], 
        p_resource_type_id INT,
        p_action_id INT,
        p_ctx JSONB
    )
    RETURNS TABLE(id INT) AS $$
    DECLARE
        v_acl_sql TEXT;
        v_final_sql TEXT;
        rec RECORD;
    BEGIN
        -- Loop through matching ACLs (NO GATEKEEPER)
        FOR rec IN
            SELECT compiled_sql
            FROM acl
            WHERE realm_id = p_realm_id
              AND resource_type_id = p_resource_type_id
              AND action_id = p_action_id
              AND (
                  (principal_id = p_principal_id)
                  OR
                  (role_id = ANY(p_role_ids))
              )
        LOOP
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                v_final_sql := 'TRUE';
            ELSE
                v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            END IF;
            
            v_acl_sql := format(
                'SELECT id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
                p_realm_id,
                p_resource_type_id,
                v_final_sql
            );
            
            RETURN QUERY EXECUTE v_acl_sql USING p_ctx;
        END LOOP;
        RETURN;
    END;
    $$ LANGUAGE plpgsql;
    """)
