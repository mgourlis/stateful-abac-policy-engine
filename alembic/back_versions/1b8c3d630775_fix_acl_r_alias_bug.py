"""fix_acl_r_alias_bug

Revision ID: 1b8c3d630775
Revises: 9d5b10607907
Create Date: 2025-12-19 13:15:06.572928

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b8c3d630775'
down_revision: Union[str, Sequence[str], None] = '9d5b10607907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        v_is_public BOOLEAN;
        rec RECORD;
    BEGIN
        -- Level 1: Floodgate (Public Flag)
        SELECT rt.is_public INTO v_is_public 
        FROM resource_type rt
        WHERE rt.id = p_resource_type_id;
        
        IF v_is_public THEN
            -- Fast Path: Return ALL resources of this type
            RETURN QUERY SELECT resource.id FROM resource WHERE resource.realm_id = p_realm_id AND resource.resource_type_id = p_resource_type_id;
            RETURN;
        END IF;

        -- Loop through matching ACLs
        FOR rec IN
            SELECT compiled_sql, resource_id
            FROM acl
            WHERE realm_id = p_realm_id
              AND resource_type_id = p_resource_type_id
              AND action_id = p_action_id
              AND (
                  (principal_id = p_principal_id)
                  OR
                  (role_id = ANY(p_role_ids))
                  OR 
                  (principal_id = 0 AND role_id = 0)
              )
        LOOP
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                v_final_sql := 'TRUE';
            ELSE
                v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            END IF;
            
            -- Level 3: Exception (Resource-Level ACL)
            IF rec.resource_id IS NOT NULL THEN
                 -- Apply specific ID restriction using 'resource.id' instead of alias
                 v_final_sql := format('resource.id = %L AND (%s)', rec.resource_id, v_final_sql);
            END IF;
            
            -- Construct Query (No alias 'r', just table name 'resource')
            v_acl_sql := format(
                'SELECT resource.id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
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
    # Revert to version with 'r' alias (from 9d5b10607907)
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
        v_is_public BOOLEAN;
        rec RECORD;
    BEGIN
        SELECT rt.is_public INTO v_is_public 
        FROM resource_type rt
        WHERE rt.id = p_resource_type_id;
        
        IF v_is_public THEN
            RETURN QUERY SELECT r.id FROM resource r WHERE r.realm_id = p_realm_id AND r.resource_type_id = p_resource_type_id;
            RETURN;
        END IF;

        FOR rec IN
            SELECT compiled_sql, resource_id
            FROM acl
            WHERE realm_id = p_realm_id
              AND resource_type_id = p_resource_type_id
              AND action_id = p_action_id
              AND (
                  (principal_id = p_principal_id)
                  OR
                  (role_id = ANY(p_role_ids))
                  OR 
                  (principal_id = 0 AND role_id = 0)
              )
        LOOP
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                v_final_sql := 'TRUE';
            ELSE
                v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            END IF;
            
            IF rec.resource_id IS NOT NULL THEN
                 v_final_sql := format('r.id = %L AND (%s)', rec.resource_id, v_final_sql);
            END IF;
            
            v_acl_sql := format(
                'SELECT r.id FROM resource r WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
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
