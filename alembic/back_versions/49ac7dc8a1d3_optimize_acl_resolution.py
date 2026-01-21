"""optimize_acl_resolution

Revision ID: 49ac7dc8a1d3
Revises: d808a294638b
Create Date: 2025-12-17 18:07:23.631072

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49ac7dc8a1d3'
down_revision: Union[str, Sequence[str], None] = 'd808a294638b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Optimize get_authorized_resources using Combined Query (OR) logic.
    Replaces Iterative Loop with Single Query logic.
    """
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
        v_conditions TEXT[] := ARRAY[]::TEXT[];
        v_final_sql TEXT;
        rec RECORD;
    BEGIN
        -- 1. Collect all Conditions from Matching ACLs
        FOR rec IN
            SELECT resource_id, compiled_sql
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
            IF rec.resource_id IS NOT NULL THEN
                -- Specific Resource Rule: Direct ID Match
                -- MUST also respect conditions if present!
                IF rec.compiled_sql IS NOT NULL AND trim(rec.compiled_sql) <> '' THEN
                     -- (id = X) AND (Conditions)
                     v_conditions := array_append(v_conditions, '(id = ' || rec.resource_id || ' AND (' || replace(rec.compiled_sql, 'p_ctx', '$1') || '))');
                ELSE
                     -- Just ID
                     v_conditions := array_append(v_conditions, 'id = ' || rec.resource_id);
                END IF;
            ELSE
                -- Class Level Rule: Use Compiled SQL
                IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                    -- Empty/Null means "Allow All" (TRUE)
                    -- If ANY rule allows ALL, we can short-circuit.
                    RETURN QUERY 
                        SELECT r.id 
                        FROM resource r 
                        WHERE r.realm_id = p_realm_id 
                          AND r.resource_type_id = p_resource_type_id;
                    RETURN; -- Halt execution
                ELSE
                    -- Append condition wrapped in parentheses
                    -- Replace placeholder if needed (though usually done at exec time, here we concat)
                    -- We must replace 'p_ctx' with '$1' for the final EXECUTE USING.
                    v_conditions := array_append(v_conditions, '(' || replace(rec.compiled_sql, 'p_ctx', '$1') || ')');
                END IF;
            END IF;
        END LOOP;

        -- 2. Execute Combined Query
        IF array_length(v_conditions, 1) > 0 THEN
            v_final_sql := array_to_string(v_conditions, ' OR ');
            
            RETURN QUERY EXECUTE format(
                'SELECT id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
                p_realm_id,
                p_resource_type_id,
                v_final_sql
            ) USING p_ctx;
        END IF;
        
        -- Default: Return Empty (No matching rules found)
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
