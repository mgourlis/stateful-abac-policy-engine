"""fix_get_authorized_resources_function

Revision ID: 1305ecc80b4d
Revises: f7601bb2bc7d
Create Date: 2025-12-17 13:42:01.961351

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1305ecc80b4d'
down_revision: Union[str, Sequence[str], None] = 'f7601bb2bc7d'
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
        -- Loop through matching ACLs
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
            -- 1. Handle NULL or Empty SQL
            -- If compiled_sql is null/empty, we assume "TRUE" (no extra restriction)
            -- This prevents the "AND <nothing>" syntax error.
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                v_final_sql := 'TRUE';
            ELSE
                -- 2. Replace placeholder with bind param ($1)
                v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            END IF;
            
            -- Construct Query
            -- We wrap v_final_sql in parens (...) for safety against OR logic in the fragment
            v_acl_sql := format(
                'SELECT id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
                p_realm_id,
                p_resource_type_id,
                v_final_sql
            );
            
            -- Execute with the JSONB parameter
            RETURN QUERY EXECUTE v_acl_sql USING p_ctx;
        END LOOP;
        RETURN;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
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
        -- Loop through matching ACLs
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
            -- Replace placeholder with bind param
            v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            
            -- Construct Query
            v_acl_sql := format(
                'SELECT id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND %s',
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
