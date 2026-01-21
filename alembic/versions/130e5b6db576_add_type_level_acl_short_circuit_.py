"""Add type-level ACL short-circuit optimization

Revision ID: 130e5b6db576
Revises: 3_auth_resource_filter
Create Date: 2025-12-24 09:15:30.403197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '130e5b6db576'
down_revision: Union[str, Sequence[str], None] = '3_auth_resource_filter'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop and recreate function with type-level short-circuit optimization
    op.execute("""
    CREATE OR REPLACE FUNCTION get_authorized_resources(
        p_realm_id INT,
        p_principal_id INT,
        p_role_ids INT[], 
        p_resource_type_id INT,
        p_action_id INT,
        p_ctx JSONB,
        p_resource_ids INT[] DEFAULT NULL
    )
    RETURNS TABLE(id INT) AS $$
    DECLARE
        v_acl_sql TEXT;
        v_final_sql TEXT;
        v_is_public BOOLEAN;
        v_resource_filter TEXT;
        v_has_type_level_access BOOLEAN := FALSE;
        rec RECORD;
    BEGIN
        -- Level 1: Floodgate (Public Flag)
        SELECT rt.is_public INTO v_is_public 
        FROM resource_type rt
        WHERE rt.id = p_resource_type_id;
        
        -- Build resource filter clause
        IF p_resource_ids IS NOT NULL THEN
            v_resource_filter := format(' AND resource.id = ANY(%L::int[])', p_resource_ids);
        ELSE
            v_resource_filter := '';
        END IF;
        
        IF v_is_public THEN
            -- Fast Path: Return ALL resources of this type (with filter if provided)
            IF p_resource_ids IS NOT NULL THEN
                RETURN QUERY SELECT resource.id FROM resource 
                    WHERE resource.realm_id = p_realm_id 
                    AND resource.resource_type_id = p_resource_type_id
                    AND resource.id = ANY(p_resource_ids);
            ELSE
                RETURN QUERY SELECT resource.id FROM resource 
                    WHERE resource.realm_id = p_realm_id 
                    AND resource.resource_type_id = p_resource_type_id;
            END IF;
            RETURN;
        END IF;

        -- OPTIMIZATION: Check for type-level ACL with no conditions (blanket access)
        -- This is a separate fast query before the main loop
        SELECT EXISTS(
            SELECT 1 FROM acl
            WHERE realm_id = p_realm_id
              AND resource_type_id = p_resource_type_id
              AND action_id = p_action_id
              AND resource_id IS NULL  -- Type-level ACL
              AND (compiled_sql IS NULL OR trim(compiled_sql) = '' OR upper(trim(compiled_sql)) = 'TRUE')  -- Unconditional access
              AND (
                  (principal_id = p_principal_id)
                  OR (role_id = ANY(p_role_ids))
                  OR (principal_id = 0 AND role_id = 0)
              )
        ) INTO v_has_type_level_access;
        
        IF v_has_type_level_access THEN
            -- Short-circuit! User has blanket access to all resources of this type
            IF p_resource_ids IS NOT NULL THEN
                RETURN QUERY SELECT resource.id FROM resource 
                    WHERE resource.realm_id = p_realm_id 
                    AND resource.resource_type_id = p_resource_type_id
                    AND resource.id = ANY(p_resource_ids);
            ELSE
                RETURN QUERY SELECT resource.id FROM resource 
                    WHERE resource.realm_id = p_realm_id 
                    AND resource.resource_type_id = p_resource_type_id;
            END IF;
            RETURN;
        END IF;

        -- Loop through matching ACLs (for conditional or resource-level access)
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
                 v_final_sql := format('resource.id = %L AND (%s)', rec.resource_id, v_final_sql);
            END IF;
            
            -- Construct Query with resource filter
            v_acl_sql := format(
                'SELECT resource.id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)%s',
                p_realm_id,
                p_resource_type_id,
                v_final_sql,
                v_resource_filter
            );
            
            RETURN QUERY EXECUTE v_acl_sql USING p_ctx;
        END LOOP;
        RETURN;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Restore previous version without type-level short-circuit
    op.execute("""
    CREATE OR REPLACE FUNCTION get_authorized_resources(
        p_realm_id INT,
        p_principal_id INT,
        p_role_ids INT[], 
        p_resource_type_id INT,
        p_action_id INT,
        p_ctx JSONB,
        p_resource_ids INT[] DEFAULT NULL
    )
    RETURNS TABLE(id INT) AS $$
    DECLARE
        v_acl_sql TEXT;
        v_final_sql TEXT;
        v_is_public BOOLEAN;
        v_resource_filter TEXT;
        rec RECORD;
    BEGIN
        SELECT rt.is_public INTO v_is_public 
        FROM resource_type rt
        WHERE rt.id = p_resource_type_id;
        
        IF p_resource_ids IS NOT NULL THEN
            v_resource_filter := format(' AND resource.id = ANY(%L::int[])', p_resource_ids);
        ELSE
            v_resource_filter := '';
        END IF;
        
        IF v_is_public THEN
            IF p_resource_ids IS NOT NULL THEN
                RETURN QUERY SELECT resource.id FROM resource 
                    WHERE resource.realm_id = p_realm_id 
                    AND resource.resource_type_id = p_resource_type_id
                    AND resource.id = ANY(p_resource_ids);
            ELSE
                RETURN QUERY SELECT resource.id FROM resource 
                    WHERE resource.realm_id = p_realm_id 
                    AND resource.resource_type_id = p_resource_type_id;
            END IF;
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
                 v_final_sql := format('resource.id = %L AND (%s)', rec.resource_id, v_final_sql);
            END IF;
            
            v_acl_sql := format(
                'SELECT resource.id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)%s',
                p_realm_id,
                p_resource_type_id,
                v_final_sql,
                v_resource_filter
            );
            
            RETURN QUERY EXECUTE v_acl_sql USING p_ctx;
        END LOOP;
        RETURN;
    END;
    $$ LANGUAGE plpgsql;
    """)
