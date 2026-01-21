"""enhanced_spatial_formats

Revision ID: 4710ef224a8e
Revises: 431deb21615f
Create Date: 2025-12-16 19:37:20.666646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4710ef224a8e'
down_revision: Union[str, Sequence[str], None] = '431deb21615f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GeoJSON and EWKT support to spatial compiler."""
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
        geom_func TEXT;
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
        args := cond->'args';
        
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
        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
            -- Determine geometry parsing function based on format
            -- GeoJSON: starts with '{'
            -- EWKT: starts with 'SRID='
            -- WKT: default
            
            IF val_text LIKE '{%' THEN
                geom_func := 'ST_SetSRID(ST_GeomFromGeoJSON(' || rhs || '), 3857)';
            ELSIF val_text LIKE 'SRID=%' THEN
                geom_func := 'ST_GeomFromEWKT(' || rhs || ')';
            ELSE
                geom_func := 'ST_GeomFromText(' || rhs || ', 3857)';
            END IF;
            
            -- Handle LHS
            IF lhs NOT LIKE 'resource.geometry' THEN
                -- Dynamic context value - parse it too
                IF lhs LIKE '%->%' THEN
                    -- It's a JSON extraction, need to parse
                    IF val_text LIKE '{%' THEN
                        lhs := 'ST_SetSRID(ST_GeomFromGeoJSON(' || lhs || '), 3857)';
                    ELSIF val_text LIKE 'SRID=%' THEN
                        lhs := 'ST_GeomFromEWKT(' || lhs || ')';
                    ELSE
                        lhs := 'ST_GeomFromText(' || lhs || ', 3857)';
                    END IF;
                END IF;
            END IF;
            
            -- Build final SQL
            IF op = 'st_dwithin' THEN
                arg_val := args #>> '{}';
                IF arg_val IS NULL THEN
                    arg_val := '0';
                END IF;
                RETURN 'ST_DWithin(' || lhs || ', ' || geom_func || ', ' || arg_val || ')';
            ELSE
                RETURN op || '(' || lhs || ', ' || geom_func || ')';
            END IF;
            
        -- STANDARD OPERATORS
        ELSE
            -- Type Detection
            IF jsonb_typeof(val) = 'number' THEN
                cast_suffix := '::numeric';
            ELSIF jsonb_typeof(val) = 'boolean' THEN
                cast_suffix := '::boolean';
            ELSE
                cast_suffix := '';
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


def downgrade() -> None:
    """Revert to WKT-only spatial support."""
    # Revert to previous version from 69e2357e1a54
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
        args := cond->'args';
        
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

        IF op = 'st_dwithin' THEN
            arg_val := args #>> '{}';
            IF arg_val IS NULL THEN
                arg_val := '0';
            END IF;
            
            IF lhs NOT LIKE 'resource.geometry' THEN
                 lhs := 'ST_GeomFromText(' || lhs || ', 3857)';
            END IF;
            
            rhs := 'ST_GeomFromText(' || rhs || ', 3857)';
            
            RETURN 'ST_DWithin(' || lhs || ', ' || rhs || ', ' || arg_val || ')';
            
        ELSIF op IN ('st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
            
            IF lhs NOT LIKE 'resource.geometry' THEN
                 lhs := 'ST_GeomFromText(' || lhs || ', 3857)';
            END IF;
            
            rhs := 'ST_GeomFromText(' || rhs || ', 3857)';
            
            RETURN op || '(' || lhs || ', ' || rhs || ')';
            
        ELSE
            IF jsonb_typeof(val) = 'number' THEN
                cast_suffix := '::numeric';
            ELSIF jsonb_typeof(val) = 'boolean' THEN
                cast_suffix := '::boolean';
            ELSE
                cast_suffix := '';
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
