"""Add NOT, NOT_IN, and ALL operator support to compile_condition_to_sql

Revision ID: add_not_operator
Revises: 58055ca375cf
Create Date: 2026-01-29

Adds support for additional logical/set operators in ACL conditions:

1. NOT - Negate a condition
   {"op": "not", "conditions": [{"op": "=", "attr": "deleted", "val": true}]}
   → NOT (resource.attributes->>'deleted' = 'true')

2. NOT_IN - Check if value is not in a list
   {"op": "not_in", "attr": "status", "val": ["deleted", "archived"]}
   → status NOT IN ('deleted', 'archived')

3. ALL - Check if array field contains all specified values
   {"op": "all", "attr": "roles", "val": ["admin", "moderator"]}
   → roles @> '["admin", "moderator"]'
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'add_not_operator'
down_revision: Union[str, Sequence[str], None] = '58055ca375cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update compile_condition_to_sql to support NOT operator."""
    
    # The function is defined in 1_init.py - we need to replace it with NOT support
    op.execute("""
    CREATE OR REPLACE FUNCTION compile_condition_to_sql(cond JSONB, ctx_var TEXT DEFAULT 'p_ctx')
    RETURNS TEXT AS $$
    DECLARE
        op TEXT;
        src TEXT;
        attr TEXT;
        val JSONB;
        args JSONB;
        sub_conditions JSONB;
        sub_sqls TEXT[] := '{}';
        i INTEGER;
        lhs TEXT;
        rhs TEXT;
        val_text TEXT;
        raw_path TEXT;
        path_parts TEXT[];
        cast_suffix TEXT := '';
        geom_func TEXT;
        arg_val TEXT;
    BEGIN
        IF cond IS NULL THEN
            RETURN 'TRUE';
        END IF;

        op := lower(cond->>'op');
        
        -- Step 1: Compound AND/OR/NOT
        IF op IN ('and', 'or', 'not') THEN
            sub_conditions := cond->'conditions';
            IF jsonb_array_length(sub_conditions) = 0 THEN
                RETURN 'TRUE';
            END IF;
            FOR i IN 0..jsonb_array_length(sub_conditions) - 1 LOOP
                sub_sqls := array_append(sub_sqls, compile_condition_to_sql(sub_conditions->i, ctx_var));
            END LOOP;
            
            -- Handle NOT operator separately
            IF op = 'not' THEN
                -- NOT wraps a single condition
                RETURN 'NOT (' || sub_sqls[1] || ')';
            ELSE
                RETURN '(' || array_to_string(sub_sqls, ' ' || upper(op) || ' ') || ')';
            END IF;
        END IF;

        -- Step 2: Leaf Node
        src := lower(coalesce(cond->>'source', 'resource'));
        attr := cond->>'attr';
        val := cond->'val';
        args := cond->'args';
        
        -- Pre-check if this is a spatial operator (needed for LHS/RHS construction)
        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
            -- For spatial operators, we need JSONB extraction (->) not text extraction (->>)
            -- Step 3: LHS for spatial
            IF src = 'resource' THEN
                IF attr = 'geometry' THEN
                    lhs := 'resource.geometry';
                ELSE
                    lhs := format('resource.attributes->%L', attr);
                END IF;
            ELSIF src = 'principal' THEN
                lhs := format('%s->''principal''->%L', ctx_var, attr);
            ELSIF src = 'context' THEN
                lhs := format('%s->''context''->%L', ctx_var, attr);
            ELSE
                IF attr = 'geometry' THEN
                    lhs := 'resource.geometry';
                ELSE
                    lhs := format('resource.attributes->%L', attr);
                END IF;
            END IF;
        ELSE
            -- Step 3: LHS for non-spatial (text extraction)
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
        END IF;

        -- Step 4: RHS with NESTED PATH SUPPORT
        val_text := val #>> '{}';
        
        IF val_text LIKE '$%' THEN
             IF val_text LIKE '$principal.%' THEN
                 raw_path := substr(val_text, 12);
                 path_parts := string_to_array(raw_path, '.');
                 rhs := format('%s->''principal''', ctx_var);
                 FOR i IN 1..array_length(path_parts, 1) LOOP
                    IF i = array_length(path_parts, 1) THEN
                        -- For spatial ops, use -> to keep JSONB; otherwise use ->> for text
                        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
                            rhs := rhs || '->' || quote_literal(path_parts[i]);
                        ELSE
                            rhs := rhs || '->>' || quote_literal(path_parts[i]);
                        END IF;
                    ELSE
                        rhs := rhs || '->' || quote_literal(path_parts[i]);
                    END IF;
                 END LOOP;
             ELSIF val_text LIKE '$context.%' THEN
                 raw_path := substr(val_text, 10);
                 path_parts := string_to_array(raw_path, '.');
                 rhs := format('%s->''context''', ctx_var);
                 FOR i IN 1..array_length(path_parts, 1) LOOP
                    IF i = array_length(path_parts, 1) THEN
                        -- For spatial ops, use -> to keep JSONB; otherwise use ->> for text
                        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
                            rhs := rhs || '->' || quote_literal(path_parts[i]);
                        ELSE
                            rhs := rhs || '->>' || quote_literal(path_parts[i]);
                        END IF;
                    ELSE
                        rhs := rhs || '->' || quote_literal(path_parts[i]);
                    END IF;
                 END LOOP;
             ELSIF val_text LIKE '$resource.%' THEN
                 -- Resource attribute reference
                 raw_path := substr(val_text, 11);
                 path_parts := string_to_array(raw_path, '.');
                 IF array_length(path_parts, 1) = 1 THEN
                    -- Simple attribute: resource.attributes->>'attr_name'
                    rhs := format('resource.attributes->>%L', path_parts[1]);
                 ELSE
                    -- Nested attribute: resource.attributes->'path'->'to'->>'attr'
                    rhs := 'resource.attributes';
                    FOR i IN 1..array_length(path_parts, 1) LOOP
                        IF i = array_length(path_parts, 1) THEN
                            rhs := rhs || '->>' || quote_literal(path_parts[i]);
                        ELSE
                            rhs := rhs || '->' || quote_literal(path_parts[i]);
                        END IF;
                    END LOOP;
                 END IF;
             ELSE
                 rhs := quote_literal(val_text);
             END IF;
        ELSIF jsonb_typeof(val) = 'array' THEN
             rhs := '(' || (SELECT string_agg(quote_literal(v #>> '{}'), ', ') FROM jsonb_array_elements(val) AS v) || ')';
        ELSIF jsonb_typeof(val) = 'boolean' THEN
             rhs := quote_literal(val::TEXT);
        ELSIF jsonb_typeof(val) = 'number' THEN
             rhs := val::TEXT;
        ELSIF jsonb_typeof(val) = 'null' THEN
             rhs := 'NULL';
        ELSE
             rhs := quote_literal(val_text);
        END IF;
        
        -- Step 5: Build expression
        -- Apply type casting for standard operators
        IF op IN ('=', '!=', '<', '>', '<=', '>=', 'in', 'not_in') THEN
            IF jsonb_typeof(val) = 'number' THEN
                cast_suffix := '::numeric';
            ELSIF jsonb_typeof(val) = 'boolean' THEN
                cast_suffix := '::boolean';
            ELSE
                cast_suffix := '';
            END IF;
            
            lhs := '(' || lhs || ')' || cast_suffix;
            rhs := '(' || rhs || ')' || cast_suffix;
        END IF;
        
        CASE op
            WHEN '=' THEN
                RETURN lhs || ' = ' || rhs;
            WHEN '!=' THEN
                RETURN lhs || ' != ' || rhs;
            WHEN '<' THEN
                RETURN lhs || ' < ' || rhs;
            WHEN '>' THEN
                RETURN lhs || ' > ' || rhs;
            WHEN '<=' THEN
                RETURN lhs || ' <= ' || rhs;
            WHEN '>=' THEN
                RETURN lhs || ' >= ' || rhs;
            WHEN 'in' THEN
                RETURN lhs || ' = ANY(ARRAY(SELECT jsonb_array_elements_text(' || quote_literal(val::text) || '::jsonb)))';
            WHEN 'not_in' THEN
                RETURN 'NOT (' || lhs || ' = ANY(ARRAY(SELECT jsonb_array_elements_text(' || quote_literal(val::text) || '::jsonb))))';
            WHEN 'all' THEN
                -- Array containment: field array contains all specified values
                -- Uses PostgreSQL @> operator
                RETURN format('%s @> %s', lhs, rhs);
            WHEN 'st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers' THEN
                -- SPATIAL OPERATORS (SRID 3857 with Transform from 4326)
                -- Parse geometry from value and transform to 3857 if needed
                IF val_text LIKE '$%' THEN
                    -- Context/Principal reference - use helper function to auto-detect format
                    geom_func := 'parse_geometry_to_3857((' || rhs || ')::text)';
                ELSIF val_text LIKE '{%' THEN
                    -- GeoJSON literal: assume 4326, transform to 3857
                    geom_func := 'ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(' || rhs || '), 4326), 3857)';
                ELSIF val_text LIKE 'SRID=3857;%' THEN
                    -- EWKT already in 3857, no transform needed
                    geom_func := 'ST_GeomFromEWKT(' || rhs || ')';
                ELSIF val_text LIKE 'SRID=%' THEN
                    -- EWKT with other SRID, transform to 3857
                    geom_func := 'ST_Transform(ST_GeomFromEWKT(' || rhs || '), 3857)';
                ELSE
                    -- Plain WKT: assume 3857, no transform needed
                    geom_func := 'ST_SetSRID(ST_GeomFromText(' || rhs || '), 3857)';
                END IF;
                
                -- Handle LHS when source is context/principal (not resource.geometry)
                IF lhs NOT LIKE 'resource.geometry' THEN
                    -- LHS is a JSONB path - use helper to auto-detect format
                    lhs := 'parse_geometry_to_3857((' || lhs || ')::text)';
                END IF;
                
                IF op = 'st_dwithin' THEN
                    arg_val := args #>> '{}';
                    IF arg_val IS NULL THEN
                        arg_val := '0';
                    END IF;
                    RETURN 'ST_DWithin(' || lhs || ', ' || geom_func || ', ' || arg_val || ')';
                ELSE
                    RETURN op || '(' || lhs || ', ' || geom_func || ')';
                END IF;
            ELSE
                RETURN 'TRUE';
        END CASE;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)


def downgrade() -> None:
    """Revert to original compile_condition_to_sql without NOT support."""
    
    # Restore the original function (without NOT support, from 1_init.py)
    op.execute("""
    CREATE OR REPLACE FUNCTION compile_condition_to_sql(cond JSONB, ctx_var TEXT DEFAULT 'p_ctx')
    RETURNS TEXT AS $$
    DECLARE
        op TEXT;
        src TEXT;
        attr TEXT;
        val JSONB;
        args JSONB;
        sub_conditions JSONB;
        sub_sqls TEXT[] := '{}';
        i INTEGER;
        lhs TEXT;
        rhs TEXT;
        val_text TEXT;
        raw_path TEXT;
        path_parts TEXT[];
        cast_suffix TEXT := '';
        geom_func TEXT;
        arg_val TEXT;
    BEGIN
        IF cond IS NULL THEN
            RETURN 'TRUE';
        END IF;

        op := lower(cond->>'op');
        
        -- Step 1: Compound AND/OR
        IF op IN ('and', 'or') THEN
            sub_conditions := cond->'conditions';
            IF jsonb_array_length(sub_conditions) = 0 THEN
                RETURN 'TRUE';
            END IF;
            FOR i IN 0..jsonb_array_length(sub_conditions) - 1 LOOP
                sub_sqls := array_append(sub_sqls, compile_condition_to_sql(sub_conditions->i, ctx_var));
            END LOOP;
            RETURN '(' || array_to_string(sub_sqls, ' ' || upper(op) || ' ') || ')';
        END IF;

        -- Step 2: Leaf Node
        src := lower(coalesce(cond->>'source', 'resource'));
        attr := cond->>'attr';
        val := cond->'val';
        args := cond->'args';
        
        -- Pre-check if this is a spatial operator (needed for LHS/RHS construction)
        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
            IF src = 'resource' THEN
                IF attr = 'geometry' THEN
                    lhs := 'resource.geometry';
                ELSE
                    lhs := format('resource.attributes->%L', attr);
                END IF;
            ELSIF src = 'principal' THEN
                lhs := format('%s->''principal''->%L', ctx_var, attr);
            ELSIF src = 'context' THEN
                lhs := format('%s->''context''->%L', ctx_var, attr);
            ELSE
                IF attr = 'geometry' THEN
                    lhs := 'resource.geometry';
                ELSE
                    lhs := format('resource.attributes->%L', attr);
                END IF;
            END IF;
        ELSE
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
        END IF;

        val_text := val #>> '{}';
        
        IF val_text LIKE '$%' THEN
             IF val_text LIKE '$principal.%' THEN
                 raw_path := substr(val_text, 12);
                 path_parts := string_to_array(raw_path, '.');
                 rhs := format('%s->''principal''', ctx_var);
                 FOR i IN 1..array_length(path_parts, 1) LOOP
                    IF i = array_length(path_parts, 1) THEN
                        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
                            rhs := rhs || '->' || quote_literal(path_parts[i]);
                        ELSE
                            rhs := rhs || '->>' || quote_literal(path_parts[i]);
                        END IF;
                    ELSE
                        rhs := rhs || '->' || quote_literal(path_parts[i]);
                    END IF;
                 END LOOP;
             ELSIF val_text LIKE '$context.%' THEN
                 raw_path := substr(val_text, 10);
                 path_parts := string_to_array(raw_path, '.');
                 rhs := format('%s->''context''', ctx_var);
                 FOR i IN 1..array_length(path_parts, 1) LOOP
                    IF i = array_length(path_parts, 1) THEN
                        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
                            rhs := rhs || '->' || quote_literal(path_parts[i]);
                        ELSE
                            rhs := rhs || '->>' || quote_literal(path_parts[i]);
                        END IF;
                    ELSE
                        rhs := rhs || '->' || quote_literal(path_parts[i]);
                    END IF;
                 END LOOP;
             ELSIF val_text LIKE '$resource.%' THEN
                 raw_path := substr(val_text, 11);
                 path_parts := string_to_array(raw_path, '.');
                 IF array_length(path_parts, 1) = 1 THEN
                    rhs := format('resource.attributes->>%L', path_parts[1]);
                 ELSE
                    rhs := 'resource.attributes';
                    FOR i IN 1..array_length(path_parts, 1) LOOP
                        IF i = array_length(path_parts, 1) THEN
                            rhs := rhs || '->>' || quote_literal(path_parts[i]);
                        ELSE
                            rhs := rhs || '->' || quote_literal(path_parts[i]);
                        END IF;
                    END LOOP;
                 END IF;
             ELSE
                 rhs := quote_literal(val_text);
             END IF;
        ELSIF jsonb_typeof(val) = 'array' THEN
             rhs := '(' || (SELECT string_agg(quote_literal(v #>> '{}'), ', ') FROM jsonb_array_elements(val) AS v) || ')';
        ELSIF jsonb_typeof(val) = 'boolean' THEN
             rhs := quote_literal(val::TEXT);
        ELSIF jsonb_typeof(val) = 'number' THEN
             rhs := val::TEXT;
        ELSIF jsonb_typeof(val) = 'null' THEN
             rhs := 'NULL';
        ELSE
             rhs := quote_literal(val_text);
        END IF;
        
        CASE op
            WHEN '=' THEN RETURN format('%s = %s', lhs, rhs);
            WHEN '!=' THEN RETURN format('%s != %s', lhs, rhs);
            WHEN '<' THEN RETURN format('(%s)::numeric < (%s)::numeric', lhs, rhs);
            WHEN '>' THEN RETURN format('(%s)::numeric > (%s)::numeric', lhs, rhs);
            WHEN '<=' THEN RETURN format('(%s)::numeric <= (%s)::numeric', lhs, rhs);
            WHEN '>=' THEN RETURN format('(%s)::numeric >= (%s)::numeric', lhs, rhs);
            WHEN 'in' THEN RETURN format('%s IN %s', lhs, rhs);
            WHEN 'st_dwithin' THEN
                arg_val := (args->>'distance')::TEXT;
                IF arg_val IS NULL THEN arg_val := args::TEXT; END IF;
                RETURN format('ST_DWithin(%s, parse_geometry_to_3857(%s), %s)', lhs, rhs, arg_val);
            WHEN 'st_contains' THEN RETURN format('ST_Contains(%s, parse_geometry_to_3857(%s))', lhs, rhs);
            WHEN 'st_within' THEN RETURN format('ST_Within(%s, parse_geometry_to_3857(%s))', lhs, rhs);
            WHEN 'st_intersects' THEN RETURN format('ST_Intersects(%s, parse_geometry_to_3857(%s))', lhs, rhs);
            WHEN 'st_covers' THEN RETURN format('ST_Covers(%s, parse_geometry_to_3857(%s))', lhs, rhs);
            ELSE RETURN 'TRUE';
        END CASE;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)
