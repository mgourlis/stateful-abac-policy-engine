"""add_get_authorization_conditions_function

Revision ID: 58055ca375cf
Revises: 5_get_permitted_actions_batch
Create Date: 2026-01-29 19:46:16.740187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '58055ca375cf'
down_revision: Union[str, Sequence[str], None] = '5_get_permitted_actions_batch'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create get_authorization_conditions function for single-query authorization."""
    op.execute("""
        CREATE OR REPLACE FUNCTION get_authorization_conditions(
            p_realm_id INT,
            p_principal_id INT,
            p_role_ids INT[],
            p_resource_type_id INT,
            p_action_id INT
        )
        RETURNS TABLE(
            filter_type TEXT,
            conditions_dsl JSONB,
            external_ids TEXT[],
            has_context_refs BOOLEAN
        ) AS $$
        DECLARE
            v_has_blanket_grant BOOLEAN := FALSE;
            v_conditions JSONB[];
            v_external_ids TEXT[];
            v_has_context_refs BOOLEAN := FALSE;
            v_acl RECORD;
        BEGIN
            -- Check for type-level blanket grant (no conditions, no resource_id)
            -- Note: Check both SQL NULL and JSON null for conditions
            SELECT EXISTS (
                SELECT 1 FROM acl a
                WHERE a.realm_id = p_realm_id
                  AND a.resource_type_id = p_resource_type_id
                  AND a.action_id = p_action_id
                  AND (a.conditions IS NULL OR a.conditions = 'null'::jsonb)
                  AND a.resource_id IS NULL
                  AND (
                      a.principal_id = p_principal_id
                      OR a.role_id = ANY(p_role_ids)
                  )
            ) INTO v_has_blanket_grant;
            
            IF v_has_blanket_grant THEN
                RETURN QUERY SELECT 'granted_all'::TEXT, NULL::JSONB, NULL::TEXT[], FALSE;
                RETURN;
            END IF;
            
            -- Collect all grant conditions and resource-level ACLs
            FOR v_acl IN
                SELECT a.conditions, e.external_id
                FROM acl a
                LEFT JOIN external_ids e ON a.resource_id = e.resource_id 
                    AND a.realm_id = e.realm_id 
                    AND a.resource_type_id = e.resource_type_id
                WHERE a.realm_id = p_realm_id
                  AND a.resource_type_id = p_resource_type_id
                  AND a.action_id = p_action_id
                  AND (
                      a.principal_id = p_principal_id
                      OR a.role_id = ANY(p_role_ids)
                  )
            LOOP
                -- Resource-level ACL (specific resource granted)
                IF v_acl.external_id IS NOT NULL THEN
                    v_external_ids := array_append(v_external_ids, v_acl.external_id);
                -- Conditional ACL (type-level with conditions)
                -- Skip if conditions is SQL NULL or JSON null
                ELSIF v_acl.conditions IS NOT NULL AND v_acl.conditions != 'null'::jsonb THEN
                    v_conditions := array_append(v_conditions, v_acl.conditions);
                    -- Check for context references
                    IF v_acl.conditions::TEXT ~ '\\$context\\.' 
                       OR v_acl.conditions::TEXT ~ '\\$principal\\.' THEN
                        v_has_context_refs := TRUE;
                    END IF;
                END IF;
            END LOOP;
            
            -- No grants found
            IF array_length(v_conditions, 1) IS NULL 
               AND array_length(v_external_ids, 1) IS NULL THEN
                RETURN QUERY SELECT 'denied_all'::TEXT, NULL::JSONB, NULL::TEXT[], FALSE;
                RETURN;
            END IF;
            
            -- Build combined conditions DSL (OR of all conditions)
            IF array_length(v_conditions, 1) > 1 THEN
                RETURN QUERY SELECT 
                    'conditions'::TEXT,
                    jsonb_build_object('op', 'or', 'conditions', to_jsonb(v_conditions)),
                    v_external_ids,
                    v_has_context_refs;
            ELSIF array_length(v_conditions, 1) = 1 THEN
                RETURN QUERY SELECT 
                    'conditions'::TEXT,
                    v_conditions[1],
                    v_external_ids,
                    v_has_context_refs;
            ELSE
                -- Only external_ids, no type-level conditions
                RETURN QUERY SELECT 
                    'conditions'::TEXT,
                    NULL::JSONB,
                    v_external_ids,
                    FALSE;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Drop get_authorization_conditions function."""
    op.execute("DROP FUNCTION IF EXISTS get_authorization_conditions(INT, INT, INT[], INT, INT);")

