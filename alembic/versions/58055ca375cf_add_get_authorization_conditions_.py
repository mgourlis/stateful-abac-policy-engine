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
    """Create get_authorization_conditions function for single-query authorization.
    
    This version merges external_ids into conditions_dsl as an IN clause,
    providing a unified DSL for SearchQuery conversion.
    
    Handles three ACL patterns:
    1. Type-level conditions: conditions only, no resource_id
    2. Resource-level unconditional: resource_id only, no conditions  
    3. Resource-level conditional: resource_id AND conditions (access to specific resource with conditions)
    """
    # asyncpg does not allow multiple statements in a single prepared call,
    # so each CREATE OR REPLACE FUNCTION is executed separately.
    op.execute("""
        CREATE OR REPLACE FUNCTION get_value_from_context(p_ctx JSONB, p_path TEXT) 
        RETURNS TEXT AS $$
        DECLARE
            v_parts TEXT[];
            v_current JSONB;
            v_key TEXT;
            i INT;
        BEGIN
            -- Path format: $context.tenant or $principal.id
            -- We assume p_ctx has structure { "context": {...}, "principal": {...} }
            
            IF p_path LIKE '$context.%' THEN
                v_current := p_ctx -> 'context';
                v_parts := string_to_array(substring(p_path FROM 10), '.');
            ELSIF p_path LIKE '$principal.%' THEN
                v_current := p_ctx -> 'principal';
                v_parts := string_to_array(substring(p_path FROM 12), '.');
            ELSE
                RETURN NULL; -- Unknown source or literal
            END IF;
            
            IF v_current IS NULL THEN 
                RETURN NULL;
            END IF;
            
            FOREACH v_key IN ARRAY v_parts
            LOOP
                IF v_current IS NULL OR jsonb_typeof(v_current) != 'object' THEN
                    RETURN NULL;
                END IF;
                v_current := v_current -> v_key;
            END LOOP;
            
            -- Return as text (unquote if string)
            IF jsonb_typeof(v_current) = 'string' THEN
                RETURN v_current #>> '{}';
            ELSIF v_current IS NULL OR jsonb_typeof(v_current) = 'null' THEN
                RETURN NULL;
            ELSE
                RETURN v_current::TEXT;
            END IF;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # asyncpg: second function in its own execute call
    op.execute("""
        CREATE OR REPLACE FUNCTION resolve_abac_condition(p_cond JSONB, p_ctx JSONB) 
        RETURNS JSONB AS $$
        DECLARE
            v_op TEXT;
            v_list JSONB;
            v_item JSONB;
            v_res JSONB;
            v_final_list JSONB[];
            
            v_source TEXT;
            v_attr TEXT;
            v_val JSONB;
            
            v_attr_val TEXT;
            v_val_resolved TEXT;
            v_val_is_ref BOOLEAN := FALSE;
            
            v_left_val TEXT;
            v_right_val TEXT;
            v_left_is_resource BOOLEAN := FALSE;
            v_right_is_resource BOOLEAN := FALSE;
            
            v_subbed_attr TEXT;
            v_subbed_val JSONB;
        BEGIN
            IF p_cond IS NULL OR p_cond = 'null'::jsonb THEN
                RETURN 'null'::jsonb; 
            END IF;

            v_op := lower(p_cond ->> 'op');
            
            -- Logical Operators
            IF v_op = 'and' THEN
                v_list := p_cond -> 'conditions';
                IF v_list IS NULL OR jsonb_array_length(v_list) = 0 THEN
                    RETURN 'true'::jsonb;
                END IF;
                
                FOREACH v_item IN ARRAY ARRAY(SELECT jsonb_array_elements(v_list))
                LOOP
                    v_res := resolve_abac_condition(v_item, p_ctx);
                    
                    IF v_res = 'false'::jsonb THEN
                        RETURN 'false'::jsonb; -- Short-circuit
                    ELSIF v_res = 'true'::jsonb OR v_res = 'null'::jsonb THEN
                        -- Skip 'true' and unknowns? No, 'null' usually implies no-op or valid.
                        -- If simplify logic: just drop 'true'.
                        NULL;
                    ELSE
                        v_final_list := array_append(v_final_list, v_res);
                    END IF;
                END LOOP;
                
                IF array_length(v_final_list, 1) IS NULL THEN
                    RETURN 'true'::jsonb; 
                ELSIF array_length(v_final_list, 1) = 1 THEN
                    RETURN v_final_list[1];
                ELSE
                    RETURN jsonb_build_object('op', 'and', 'conditions', to_jsonb(v_final_list));
                END IF;

            ELSIF v_op = 'or' THEN
                v_list := p_cond -> 'conditions';
                IF v_list IS NULL OR jsonb_array_length(v_list) = 0 THEN
                    RETURN 'false'::jsonb;
                END IF;
                
                FOREACH v_item IN ARRAY ARRAY(SELECT jsonb_array_elements(v_list))
                LOOP
                    v_res := resolve_abac_condition(v_item, p_ctx);
                    
                    IF v_res = 'true'::jsonb THEN
                        RETURN 'true'::jsonb; -- Short-circuit
                    ELSIF v_res = 'false'::jsonb THEN
                        -- Skip 'false'
                        NULL;
                    ELSE
                        v_final_list := array_append(v_final_list, v_res);
                    END IF;
                END LOOP;
                
                IF array_length(v_final_list, 1) IS NULL THEN
                    RETURN 'false'::jsonb; 
                ELSIF array_length(v_final_list, 1) = 1 THEN
                    RETURN v_final_list[1];
                ELSE
                    RETURN jsonb_build_object('op', 'or', 'conditions', to_jsonb(v_final_list));
                END IF;
                
            ELSIF v_op = 'not' THEN
                v_res := resolve_abac_condition(p_cond -> 'condition', p_ctx);
                IF v_res = 'true'::jsonb THEN RETURN 'false'::jsonb; END IF;
                IF v_res = 'false'::jsonb THEN RETURN 'true'::jsonb; END IF;
                RETURN jsonb_build_object('op', 'not', 'condition', v_res);
            END IF;
            
            -- Leaf Conditions
            v_source := p_cond ->> 'source';
            v_attr := p_cond ->> 'attr';
            v_val := p_cond -> 'val';
            
            -- 1. Resolve LHS (Attribute)
            IF v_source = 'context' THEN
                v_left_val := get_value_from_context(p_ctx, '$context.' || v_attr);
                v_subbed_attr := v_left_val; -- For substitution
            ELSIF v_source = 'principal' THEN
                v_left_val := get_value_from_context(p_ctx, '$principal.' || v_attr);
                v_subbed_attr := v_left_val;
            ELSE 
                -- Resource or unknown
                v_left_val := NULL;
                v_left_is_resource := TRUE;
            END IF;
            
            -- 2. Resolve RHS (Value)
            IF jsonb_typeof(v_val) = 'string' AND (v_val #>> '{}') LIKE '$%' THEN
                 v_val_resolved := get_value_from_context(p_ctx, v_val #>> '{}');
                 IF v_val_resolved IS NULL AND (v_val #>> '{}') LIKE '$resource.%' THEN
                     v_right_is_resource := TRUE;
                 ELSE
                     -- It was a context/principal ref that resolved (or failed to null)
                     NULL;
                 END IF;
                 
                 IF v_val_resolved IS NOT NULL THEN
                    v_subbed_val := to_jsonb(v_val_resolved);
                 ELSE
                    -- Keep original if resource ref
                    v_subbed_val := v_val; 
                 END IF;
            ELSE
                 -- Literal
                 IF jsonb_typeof(v_val) = 'string' THEN
                    v_val_resolved := v_val #>> '{}';
                 ELSE
                    v_val_resolved := v_val::text; -- Basic string conversion for eval
                 END IF;
                 v_subbed_val := v_val;
            END IF;

            -- 3. Evaluate if fully resolvable (NO resource refs)
            IF NOT v_left_is_resource AND NOT v_right_is_resource THEN
                -- Both are values available now. Evaluate!
                IF v_left_val IS NULL OR v_val_resolved IS NULL THEN
                    -- Special handling for NULLs if needed, or simpl return false
                    -- But let's check basic equality
                    IF v_op = 'is_null' THEN RETURN to_jsonb(v_left_val IS NULL); END IF;
                    IF v_op = 'is_not_null' THEN RETURN to_jsonb(v_left_val IS NOT NULL); END IF;
                END IF;

                IF v_op = '=' OR v_op = '==' THEN
                    RETURN to_jsonb(v_left_val = v_val_resolved);
                ELSIF v_op = '!=' OR v_op = '<>' THEN
                    RETURN to_jsonb(v_left_val IS DISTINCT FROM v_val_resolved);
                ELSIF v_op = 'in' THEN
                     -- v_val is array
                     RETURN to_jsonb(v_val @> to_jsonb(v_left_val));
                END IF;
                
                -- Fallback for unknown ops: return simplified object
            END IF;
            
            -- 4. Return Substitution Result (Partially Resolved)
            RETURN jsonb_build_object(
                'op', p_cond -> 'op',
                'source', CASE WHEN v_left_is_resource THEN 'resource' ELSE 'static' END,
                'attr', CASE WHEN v_left_is_resource THEN p_cond -> 'attr' ELSE to_jsonb(v_left_val) END,
                'val', v_subbed_val
            );
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # asyncpg: third function in its own execute call
    op.execute("""
        CREATE OR REPLACE FUNCTION get_authorization_conditions(
            p_realm_id INT,
            p_principal_id INT,
            p_role_ids INT[],
            p_resource_type_id INT,
            p_action_id INT,
            p_ctx JSONB default '{}'::jsonb
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
            v_unconditional_external_ids TEXT[];
            v_has_context_refs BOOLEAN := FALSE;
            v_acl RECORD;
            v_final_conditions JSONB[];
            v_external_ids_condition JSONB;
            v_resource_with_condition JSONB;
            v_has_valid_conditions BOOLEAN;
            v_res_cond JSONB;
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
            -- Group by conditions to consolidate identical policies
            FOR v_acl IN
                SELECT 
                    a.conditions, 
                    array_agg(e.external_id) FILTER (WHERE e.external_id IS NOT NULL) as resource_ids,
                    bool_or(a.resource_id IS NULL) as is_type_level
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
                GROUP BY a.conditions
            LOOP
                -- Check if conditions are valid (not NULL and not JSON null)
                v_has_valid_conditions := v_acl.conditions IS NOT NULL 
                                          AND v_acl.conditions != 'null'::jsonb;
                
                -- OPTIMIZATION: Resolve & Simplify
                -- We try to resolve to TRUE/FALSE or a Simplified Object
                v_res_cond := NULL;
                IF v_has_valid_conditions THEN
                    v_res_cond := resolve_abac_condition(v_acl.conditions, p_ctx);
                    
                    IF v_res_cond = 'false'::jsonb THEN
                        -- Condition failed! Skip this group entirely
                        CONTINUE;
                    END IF;
                END IF;

                IF v_has_valid_conditions AND v_res_cond != 'true'::jsonb THEN
                    -- Case: Valid condition that is PARTIAL (object)
                    -- We include the Simplified Condition
                    
                    -- Check for context references in the *resolved* version?
                    -- Usually they are gone now, but keeping flag doesn't hurt.
                     IF v_res_cond::TEXT ~ '\\$context\\.' 
                       OR v_res_cond::TEXT ~ '\\$principal\\.' THEN
                        v_has_context_refs := TRUE;
                    END IF;

                    IF v_acl.is_type_level THEN
                        v_conditions := array_append(v_conditions, v_res_cond);
                    ELSE
                        -- Resource-level ACL WITH conditions
                        IF array_length(v_acl.resource_ids, 1) > 1 THEN
                            v_resource_with_condition := jsonb_build_object(
                                'op', 'and',
                                'conditions', jsonb_build_array(
                                    jsonb_build_object(
                                        'op', 'in',
                                        'source', 'resource',
                                        'attr', 'external_id',
                                        'val', to_jsonb(v_acl.resource_ids)
                                    ),
                                    v_res_cond
                                )
                            );
                            v_conditions := array_append(v_conditions, v_resource_with_condition);
                        ELSIF array_length(v_acl.resource_ids, 1) = 1 THEN
                             v_resource_with_condition := jsonb_build_object(
                                'op', 'and',
                                'conditions', jsonb_build_array(
                                    jsonb_build_object(
                                        'op', '=',
                                        'source', 'resource',
                                        'attr', 'external_id',
                                        'val', v_acl.resource_ids[1]
                                    ),
                                    v_res_cond
                                )
                            );
                            v_conditions := array_append(v_conditions, v_resource_with_condition);
                        END IF;
                    END IF;
                ELSE
                    -- Post-Eval is Unconditional (True or No-Op)
                    
                    IF v_acl.is_type_level THEN
                        RETURN QUERY SELECT 'granted_all'::TEXT, NULL::JSONB, NULL::TEXT[], FALSE;
                        RETURN;
                    ELSE
                        IF v_acl.resource_ids IS NOT NULL THEN
                             v_unconditional_external_ids := COALESCE(v_unconditional_external_ids, ARRAY[]::TEXT[]) || v_acl.resource_ids;
                        END IF;
                    END IF;
                END IF;
            END LOOP;
            
            -- No grants found
            IF array_length(v_conditions, 1) IS NULL 
               AND array_length(v_unconditional_external_ids, 1) IS NULL THEN
                RETURN QUERY SELECT 'denied_all'::TEXT, NULL::JSONB, NULL::TEXT[], FALSE;
                RETURN;
            END IF;
            
            -- Build unified conditions_dsl (merged)
            v_final_conditions := v_conditions;
            
            IF array_length(v_unconditional_external_ids, 1) > 0 THEN
                v_external_ids_condition := jsonb_build_object(
                    'op', 'in',
                    'source', 'resource',
                    'attr', 'external_id',
                    'val', to_jsonb(v_unconditional_external_ids)
                );
                v_final_conditions := array_append(v_final_conditions, v_external_ids_condition);
            END IF;
            
            IF array_length(v_final_conditions, 1) > 1 THEN
                RETURN QUERY SELECT 
                    'conditions'::TEXT,
                    jsonb_build_object('op', 'or', 'conditions', to_jsonb(v_final_conditions)),
                    NULL::TEXT[],
                    v_has_context_refs;
            ELSIF array_length(v_final_conditions, 1) = 1 THEN
                RETURN QUERY SELECT 
                    'conditions'::TEXT,
                    v_final_conditions[1],
                    NULL::TEXT[],
                    v_has_context_refs;
            ELSE
                RETURN QUERY SELECT 'denied_all'::TEXT, NULL::JSONB, NULL::TEXT[], FALSE;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Drop get_authorization_conditions function."""
    op.execute("DROP FUNCTION IF EXISTS get_authorization_conditions(INT, INT, INT[], INT, INT);")

