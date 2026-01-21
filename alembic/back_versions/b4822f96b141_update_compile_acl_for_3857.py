"""update_compile_acl_for_3857

Revision ID: b4822f96b141
Revises: 1b8c3d630775
Create Date: 2025-12-19 22:05:40.861294

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4822f96b141'
down_revision: Union[str, Sequence[str], None] = '1b8c3d630775'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update compile_condition_to_sql function for SRID 3857 with transform support."""
    
    # Also update the geometry column to SRID 3857
    op.execute("""
    ALTER TABLE resource 
    ALTER COLUMN geometry TYPE geometry(Geometry, 3857) 
    USING ST_Transform(COALESCE(geometry, ST_GeomFromText('POINT(0 0)', 4326)), 3857);
    """)
    
    # Update the compile_condition_to_sql function with SRID 3857 transform logic
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
        
        -- Step 4: RHS with NESTED PATH SUPPORT
        val_text := val #>> '{}';
        
        IF val_text LIKE '$%' THEN
             IF val_text LIKE '$principal.%' THEN
                 raw_path := substr(val_text, 12);
                 path_parts := string_to_array(raw_path, '.');
                 rhs := format('%s->''principal''', ctx_var);
                 FOR i IN 1..array_length(path_parts, 1) LOOP
                    IF i = array_length(path_parts, 1) THEN
                        rhs := rhs || '->>' || quote_literal(path_parts[i]);
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
                        rhs := rhs || '->>' || quote_literal(path_parts[i]);
                    ELSE
                        rhs := rhs || '->' || quote_literal(path_parts[i]);
                    END IF;
                 END LOOP;
             ELSE
                 rhs := quote_literal(val_text);
             END IF;
        ELSE
             rhs := quote_literal(val_text);
        END IF;

        -- Step 5: Operator & Casting Logic
        
        -- SPATIAL OPERATORS
        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
            -- Parse geometry from value and transform to 3857 if needed
            IF val_text LIKE '{%' THEN
                -- GeoJSON: assume 4326, transform to 3857
                geom_func := 'ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(' || rhs || '), 4326), 3857)';
            ELSIF val_text LIKE 'SRID=3857;%' THEN
                -- EWKT already in 3857, no transform needed
                geom_func := 'ST_GeomFromEWKT(' || rhs || ')';
            ELSIF val_text LIKE 'SRID=%' THEN
                -- EWKT with other SRID, transform to 3857
                geom_func := 'ST_Transform(ST_GeomFromEWKT(' || rhs || '), 3857)';
            ELSE
                -- Plain WKT: assume 4326, transform to 3857
                geom_func := 'ST_Transform(ST_GeomFromText(' || rhs || ', 4326), 3857)';
            END IF;
            
            -- Handle LHS (context variables, etc.)
            IF lhs NOT LIKE 'resource.geometry' THEN
                IF lhs LIKE '%->' THEN
                    IF val_text LIKE '{%' THEN
                        lhs := 'ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(' || lhs || '), 4326), 3857)';
                    ELSIF val_text LIKE 'SRID=3857;%' THEN
                        lhs := 'ST_GeomFromEWKT(' || lhs || ')';
                    ELSIF val_text LIKE 'SRID=%' THEN
                        lhs := 'ST_Transform(ST_GeomFromEWKT(' || lhs || '), 3857)';
                    ELSE
                        lhs := 'ST_Transform(ST_GeomFromText(' || lhs || ', 4326), 3857)';
                    END IF;
                END IF;
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
            
        -- STANDARD OPERATORS
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


def downgrade() -> None:
    """Revert to SRID 4326."""
    op.execute("""
    ALTER TABLE resource 
    ALTER COLUMN geometry TYPE geometry(Geometry, 4326) 
    USING ST_Transform(COALESCE(geometry, ST_GeomFromText('POINT(0 0)', 3857)), 4326);
    """)
