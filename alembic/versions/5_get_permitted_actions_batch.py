"""Add get_permitted_actions_batch function

Revision ID: 5_get_permitted_actions_batch
Revises: 130e5b6db576
Create Date: 2026-01-01

Creates a new PostgreSQL function that returns ALL permitted (resource_id, action_id) 
pairs in a single query, avoiding the O(resources × actions) overhead.
"""
from typing import Sequence, Union
from alembic import op


revision: str = '5_get_permitted_actions_batch'
down_revision: Union[str, Sequence[str], None] = '130e5b6db576'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION get_permitted_actions_batch(
        p_realm_id INT,
        p_principal_id INT,
        p_role_ids INT[],
        p_resource_type_id INT,
        p_resource_ids INT[] DEFAULT NULL,
        p_ctx JSONB DEFAULT '{}'::jsonb
    )
    RETURNS TABLE(
        resource_id INT,
        action_id INT,
        is_type_level BOOLEAN
    ) AS $$
    DECLARE
        v_is_public BOOLEAN;
        v_all_action_ids INT[];
        rec RECORD;
        v_final_sql TEXT;
        v_acl_sql TEXT;
        v_resource_filter TEXT;
    BEGIN
        -- Get public flag for this resource type
        SELECT rt.is_public INTO v_is_public 
        FROM resource_type rt
        WHERE rt.id = p_resource_type_id;
        
        -- Get all actions for this realm
        SELECT array_agg(DISTINCT a.id) INTO v_all_action_ids
        FROM action a
        WHERE a.realm_id = p_realm_id;
        
        -- Build resource filter
        IF p_resource_ids IS NOT NULL THEN
            v_resource_filter := format(' AND r.id = ANY(%L::int[])', p_resource_ids);
        ELSE
            v_resource_filter := '';
        END IF;
        
        -- Level 1: Public resource type - ALL actions permitted for ALL resources
        IF v_is_public THEN
            RETURN QUERY 
                SELECT r.id, unnest(v_all_action_ids), FALSE
                FROM resource r
                WHERE r.realm_id = p_realm_id 
                AND r.resource_type_id = p_resource_type_id
                AND (p_resource_ids IS NULL OR r.id = ANY(p_resource_ids));
            RETURN;
        END IF;
        
        -- Level 2: Type-level ACLs (blanket access to all resources for specific actions)
        -- These are ACLs where resource_id IS NULL
        RETURN QUERY
            SELECT r.id, acl.action_id, TRUE
            FROM acl
            CROSS JOIN resource r
            WHERE acl.realm_id = p_realm_id
              AND acl.resource_type_id = p_resource_type_id
              AND acl.resource_id IS NULL  -- Type-level
              AND (acl.compiled_sql IS NULL OR trim(acl.compiled_sql) = '' OR upper(trim(acl.compiled_sql)) = 'TRUE')
              AND (
                  acl.principal_id = p_principal_id
                  OR acl.role_id = ANY(p_role_ids)
                  OR (acl.principal_id = 0 AND acl.role_id = 0)
              )
              AND r.realm_id = p_realm_id
              AND r.resource_type_id = p_resource_type_id
              AND (p_resource_ids IS NULL OR r.id = ANY(p_resource_ids));
        
        -- Level 3: Resource-level ACLs (specific resource grants)
        FOR rec IN
            SELECT acl.action_id, acl.resource_id, acl.compiled_sql
            FROM acl
            WHERE acl.realm_id = p_realm_id
              AND acl.resource_type_id = p_resource_type_id
              AND acl.resource_id IS NOT NULL  -- Resource-level only
              AND (
                  acl.principal_id = p_principal_id
                  OR acl.role_id = ANY(p_role_ids)
                  OR (acl.principal_id = 0 AND acl.role_id = 0)
              )
        LOOP
            -- Check if this resource is in our filter
            IF p_resource_ids IS NOT NULL AND NOT (rec.resource_id = ANY(p_resource_ids)) THEN
                CONTINUE;
            END IF;
            
            -- Check condition
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                -- Unconditional access
                RETURN QUERY SELECT rec.resource_id, rec.action_id, FALSE;
            ELSE
                -- Evaluate context condition
                BEGIN
                    v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
                    EXECUTE format('SELECT 1 WHERE %s', v_final_sql) USING p_ctx;
                    IF FOUND THEN
                        RETURN QUERY SELECT rec.resource_id, rec.action_id, FALSE;
                    END IF;
                EXCEPTION WHEN OTHERS THEN
                    -- Skip on error
                    NULL;
                END;
            END IF;
        END LOOP;
        
        RETURN;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_permitted_actions_batch(INT, INT, INT[], INT, INT[], JSONB)")
