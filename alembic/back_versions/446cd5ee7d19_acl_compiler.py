"""acl_compiler

Revision ID: 446cd5ee7d19
Revises: 146870ccf5ed
Create Date: 2025-12-16 17:39:12.995932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '446cd5ee7d19'
down_revision: Union[str, Sequence[str], None] = '146870ccf5ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Compile Function
    op.execute("""
    CREATE OR REPLACE FUNCTION compile_condition_to_sql(cond JSONB, ctx_var TEXT)
    RETURNS TEXT AS $$
    DECLARE
        op TEXT;
        val JSONB;
        cond_list JSONB;
        res_list TEXT[] := ARRAY[]::TEXT[];
        child_sql TEXT;
        cond_item JSONB;
        lhs TEXT;
        rhs TEXT;
        cast_suffix TEXT;
        src TEXT;
        attr TEXT;
        val_text TEXT;
    BEGIN
        -- Step 1: Extract fields
        op := cond->>'op';
        
        -- Step 2: Recursive AND/OR
        IF op IN ('and', 'or') THEN
            cond_list := cond->'conditions';
            FOR cond_item IN SELECT * FROM jsonb_array_elements(cond_list)
            LOOP
                child_sql := compile_condition_to_sql(cond_item, ctx_var);
                res_list := array_append(res_list, child_sql);
            END LOOP;
            
            IF op = 'and' THEN
                RETURN '(' || array_to_string(res_list, ' AND ') || ')';
            ELSE
                RETURN '(' || array_to_string(res_list, ' OR ') || ')';
            END IF;
        END IF;

        -- Standard Condition
        src := cond->>'source';
        attr := cond->>'attr';
        val := cond->'val';
        
        -- Step 3: Type Detection
        IF jsonb_typeof(val) = 'number' THEN
            cast_suffix := '::numeric';
        ELSIF jsonb_typeof(val) = 'boolean' THEN
            cast_suffix := '::boolean';
        ELSE
            cast_suffix := '';
        END IF;
        
        -- Step 4: LHS
        IF src = 'resource' THEN
            lhs := format('resource.attributes->>%L', attr);
        ELSIF src = 'principal' THEN
            lhs := format('%s->''principal''->>%L', ctx_var, attr);
        ELSIF src = 'context' THEN
            lhs := format('%s->''context''->>%L', ctx_var, attr);
        ELSE
            lhs := format('resource.attributes->>%L', attr); -- Default to resource if source missing
        END IF;
        lhs := '(' || lhs || ')' || cast_suffix;
        
        -- Step 5: RHS
        val_text := val #>> '{}';
        IF val_text LIKE '$%' THEN
             -- Parse placeholder e.g. $principal.dept
             IF val_text LIKE '$principal.%' THEN
                 rhs := format('%s->''principal''->>%L', ctx_var, substr(val_text, 12)); -- length('$principal.')+1 = 12
             ELSIF val_text LIKE '$context.%' THEN
                 rhs := format('%s->''context''->>%L', ctx_var, substr(val_text, 10)); -- length('$context.')+1 = 10
             ELSE
                 rhs := quote_literal(val_text);
             END IF;
        ELSE
             rhs := quote_literal(val_text);
        END IF;
        rhs := '(' || rhs || ')' || cast_suffix;
        
        -- Step 6: Final Assembly
        IF op = 'in' THEN
            -- Handle IN with ANY(ARRAY(...))
            -- val is expected to be a JSON array, e.g. [1, 2] or ["a", "b"]
            -- We extract as text array so strict typing might be loose unless cast_suffix used on LHS matches
            -- If cast_suffix is ::numeric, we should cast array elements?
            -- Original plan: Return lhs || ' = ANY(ARRAY(SELECT jsonb_array_elements_text(' || quote_literal(val) || '::jsonb)))'
            -- This works for text comparison. If LHS is numeric, strict SQL might require casting elements.
            -- But "jsonb_array_elements_text" returns text.
            -- If we trust postgres implicit cast or if we add explicit cast to the array elements?
            -- To be safe, rely on LHS cast being consistent with RHS literal.
            RETURN lhs || ' = ANY(ARRAY(SELECT jsonb_array_elements_text(' || quote_literal(val::text) || '::jsonb)))';
        ELSE
            RETURN lhs || ' ' || op || ' ' || rhs;
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # Trigger Function
    op.execute("""
    CREATE OR REPLACE FUNCTION trg_compile_acl_conditions_func()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.conditions IS NULL THEN
            NEW.compiled_sql := 'TRUE';
        ELSE
            NEW.compiled_sql := compile_condition_to_sql(NEW.conditions, 'p_ctx');
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # Attach Trigger
    op.execute("""
    CREATE TRIGGER trg_compile_acl_conditions
    BEFORE INSERT OR UPDATE ON acl
    FOR EACH ROW
    EXECUTE FUNCTION trg_compile_acl_conditions_func();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_compile_acl_conditions ON acl")
    op.execute("DROP FUNCTION IF EXISTS trg_compile_acl_conditions_func")
    op.execute("DROP FUNCTION IF EXISTS compile_condition_to_sql")
