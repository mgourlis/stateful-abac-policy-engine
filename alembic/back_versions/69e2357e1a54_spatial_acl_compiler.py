"""spatial_acl_compiler

Revision ID: 69e2357e1a54
Revises: 0a8b4719fad6
Create Date: 2025-12-16 18:24:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69e2357e1a54'
down_revision: Union[str, Sequence[str], None] = '2dd87038dfeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Compile Function with Spatial Support and Operator Precedence Fix
    op.execute("""
    CREATE OR REPLACE FUNCTION compile_condition_to_sql(cond JSONB, ctx_var TEXT)
    RETURNS TEXT AS $$
    DECLARE
        op TEXT;
        val JSONB;
        args JSONB;
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
        arg_val TEXT;
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
        args := cond->'args'; -- For ST_DWithin(geom, geom, distance)
        
        -- Step 3: LHS
        IF src = 'resource' THEN
            IF attr = 'geometry' THEN
                lhs := 'resource.geometry';
            ELSE
                lhs := format('resource.attributes->>%L', attr);
            END IF;
        ELSIF src = 'principal' THEN
            lhs := format('%s->''principal''->>%L', ctx_var, attr);
        ELSIF src = 'context' THEN
            lhs := format('%s->''context''->>%L', ctx_var, attr);
        ELSE
            IF attr = 'geometry' THEN
                lhs := 'resource.geometry';
            ELSE
                lhs := format('resource.attributes->>%L', attr);
            END IF;
        END IF;
        
        -- Step 4: RHS
        val_text := val #>> '{}';
        
        IF val_text LIKE '$%' THEN
             -- Parse placeholder e.g. $principal.dept
             IF val_text LIKE '$principal.%' THEN
                 rhs := format('%s->''principal''->>%L', ctx_var, substr(val_text, 12));
             ELSIF val_text LIKE '$context.%' THEN
                 rhs := format('%s->''context''->>%L', ctx_var, substr(val_text, 10));
             ELSE
                 rhs := quote_literal(val_text);
             END IF;
        ELSE
             rhs := quote_literal(val_text);
        END IF;

        -- Step 5: Operator & Casting Logic
        
        -- SPATIAL OPERATORS
        IF op = 'st_dwithin' THEN
            -- ST_DWithin(lhs, rhs, distance)
            -- LHS is ideally geometry. RHS must be cast to geometry.
            -- If user provided WKT string as val, we cast it.
            -- args is distance in meters (if 3857/geography or projected units)
            arg_val := args #>> '{}';
            IF arg_val IS NULL THEN
                arg_val := '0';
            END IF;
            
            -- We assume LHS is already a geometry (if attr='geometry') or needs cast?
            -- If src=principal/context, it comes as text. Need cast.
            IF lhs LIKE 'resource.geometry' THEN
                 -- Native column, good.
                 NULL;
            ELSE
                 lhs := 'ST_GeomFromText(' || lhs || ', 3857)';
            END IF;
            
            -- RHS casting
            -- If dynamic placeholder, it returns text. If literal, it is text.
            rhs := 'ST_GeomFromText(' || rhs || ', 3857)';
            
            RETURN 'ST_DWithin(' || lhs || ', ' || rhs || ', ' || arg_val || ')';
            
        ELSIF op IN ('st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
            -- ST_Contains(lhs, rhs)
            
            IF lhs NOT LIKE 'resource.geometry' THEN
                 lhs := 'ST_GeomFromText(' || lhs || ', 3857)';
            END IF;
            
            rhs := 'ST_GeomFromText(' || rhs || ', 3857)';
            
            RETURN op || '(' || lhs || ', ' || rhs || ')';
            
        -- STANDARD OPERATORS
        ELSE
            -- Type Detection
            IF jsonb_typeof(val) = 'number' THEN
                cast_suffix := '::numeric';
            ELSIF jsonb_typeof(val) = 'boolean' THEN
                cast_suffix := '::boolean';
            ELSE
                cast_suffix := ''; -- Default text
            END IF;
            
            lhs := '(' || lhs || ')' || cast_suffix;
            rhs := '(' || rhs || ')' || cast_suffix;
            
            IF op = 'in' THEN
                 RETURN lhs || ' = ANY(ARRAY(SELECT jsonb_array_elements_text(' || quote_literal(val::text) || '::jsonb)))';
            ELSE
                 RETURN lhs || ' ' || op || ' ' || rhs;
            END IF;
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # Trigger Re-Apply not strictly needed as function signature is same and replaced using CREATE OR REPLACE.
    # But safe to ensure dependencies.
    # Actually, trigger refers to function by name. Updating function body is sufficient.


def downgrade() -> None:
    # Revert to the version from 0a8b4719fad6 / 446cd5ee7d19 (Standard compiler without spatial)
    # We copy the text from the previous migration.
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
        op := cond->>'op';
        
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

        src := cond->>'source';
        attr := cond->>'attr';
        val := cond->'val';
        
        IF jsonb_typeof(val) = 'number' THEN
            cast_suffix := '::numeric';
        ELSIF jsonb_typeof(val) = 'boolean' THEN
            cast_suffix := '::boolean';
        ELSE
            cast_suffix := '';
        END IF;
        
        IF src = 'resource' THEN
            lhs := format('resource.attributes->>%L', attr);
        ELSIF src = 'principal' THEN
            lhs := format('%s->''principal''->>%L', ctx_var, attr);
        ELSIF src = 'context' THEN
            lhs := format('%s->''context''->>%L', ctx_var, attr);
        ELSE
            lhs := format('resource.attributes->>%L', attr);
        END IF;
        lhs := '(' || lhs || ')' || cast_suffix;
        
        val_text := val #>> '{}';
        IF val_text LIKE '$%' THEN
             IF val_text LIKE '$principal.%' THEN
                 rhs := format('%s->''principal''->>%L', ctx_var, substr(val_text, 12));
             ELSIF val_text LIKE '$context.%' THEN
                 rhs := format('%s->''context''->>%L', ctx_var, substr(val_text, 10));
             ELSE
                 rhs := quote_literal(val_text);
             END IF;
        ELSE
             rhs := quote_literal(val_text);
        END IF;
        rhs := '(' || rhs || ')' || cast_suffix;
        
        IF op = 'in' THEN
            RETURN lhs || ' = ANY(ARRAY(SELECT jsonb_array_elements_text(' || quote_literal(val::text) || '::jsonb)))';
        ELSE
            RETURN lhs || ' ' || op || ' ' || rhs;
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)
