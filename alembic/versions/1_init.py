"""1_init - Consolidated Schema

Revision ID: 1_init
Revises: 
Create Date: 2025-12-19

This migration consolidates all schema migrations into a single initial migration.
Includes:
- Base identity tables (realm, resource_type, action, principal, auth_role)
- Partitioned tables (resource, acl, external_ids)
- Keycloak config with sync_groups
- ACL compiler with SRID 3857 spatial support
- Authorization runner with public access floodgate
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1_init'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable PostGIS Extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ========================================================================
    # 2. BASE IDENTITY TABLES
    # ========================================================================
    
    # Realm
    op.create_table(
        'realm',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Resource Type (with is_public for floodgate)
    op.create_table(
        'resource_type',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', 'name', name='uq_resource_type_realm_name')
    )
    op.create_index(op.f('ix_resource_type_is_public'), 'resource_type', ['is_public'], unique=False)

    # Action
    op.create_table(
        'action',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', 'name', name='uq_action_realm_name')
    )

    # Principal
    op.create_table(
        'principal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Auth Role
    op.create_table(
        'auth_role',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Principal Roles
    op.create_table(
        'principal_roles',
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['principal_id'], ['principal.id'], ),
        sa.ForeignKeyConstraint(['role_id'], ['auth_role.id'], ),
        sa.PrimaryKeyConstraint('principal_id', 'role_id')
    )

    # Authorization Log
    op.create_table(
        'authorization_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('action_name', sa.String(), nullable=True),
        sa.Column('resource_type_name', sa.String(), nullable=True),
        sa.Column('decision', sa.Boolean(), nullable=False),
        sa.Column('resource_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('external_resource_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Keycloak Config
    op.create_table(
        'realm_keycloak_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.Column('server_url', sa.String(), nullable=False),
        sa.Column('keycloak_realm', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('client_secret', sa.String(), nullable=True),
        sa.Column('verify_ssl', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sync_cron', sa.String(), nullable=True),
        sa.Column('sync_groups', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', name='uq_realm_keycloak_realm_id')
    )

    # ========================================================================
    # 3. PARTITIONED TABLES
    # ========================================================================
    
    # Resource Table (Partitioned, SRID 3857)
    op.execute("""
    CREATE TABLE resource (
        id SERIAL NOT NULL,
        realm_id INT NOT NULL REFERENCES realm(id),
        resource_type_id INT NOT NULL REFERENCES resource_type(id),
        geometry GEOMETRY(Geometry, 3857),
        attributes JSONB NOT NULL DEFAULT '{}',
        PRIMARY KEY (id, realm_id, resource_type_id)
    ) PARTITION BY LIST (realm_id);
    """)

    # ACL Table (Partitioned with auto-id sequence)
    op.execute("CREATE SEQUENCE IF NOT EXISTS acl_id_seq")
    
    op.execute("""
    CREATE TABLE acl (
        id INT NOT NULL DEFAULT nextval('acl_id_seq'),
        principal_id INT,
        role_id INT,
        realm_id INT NOT NULL,
        resource_type_id INT NOT NULL,
        resource_id INT,
        action_id INT NOT NULL,
        conditions JSONB,
        compiled_sql TEXT,
        CHECK (
            (principal_id != 0 AND role_id = 0) OR
            (principal_id = 0 AND role_id != 0)
        ),
        PRIMARY KEY (realm_id, resource_type_id, id)
    ) PARTITION BY LIST (realm_id);
    """)
    
    # Functional Unique Index
    op.execute("""
        CREATE UNIQUE INDEX idx_acl_unique_rule 
        ON acl (realm_id, resource_type_id, action_id, principal_id, role_id, COALESCE(resource_id, -1))
    """)

    # External IDs Table (Partitioned)
    op.execute("""
    CREATE TABLE external_ids (
        resource_id INT NOT NULL,
        realm_id INT NOT NULL,
        resource_type_id INT NOT NULL,
        external_id TEXT NOT NULL,
        PRIMARY KEY (realm_id, resource_type_id, external_id),
        FOREIGN KEY (resource_id, realm_id, resource_type_id) REFERENCES resource (id, realm_id, resource_type_id) ON DELETE CASCADE,
        FOREIGN KEY (resource_type_id) REFERENCES resource_type(id)
    ) PARTITION BY LIST (realm_id);
    """)

    # ========================================================================
    # 4. GEOMETRY PARSING HELPER (Auto-detect format, normalize to SRID 3857)
    # ========================================================================
    op.execute("""
    CREATE OR REPLACE FUNCTION parse_geometry_to_3857(geom_text TEXT)
    RETURNS geometry AS $$
    DECLARE
        result geometry;
        srid_part TEXT;
        wkt_part TEXT;
        extracted_srid INT;
    BEGIN
        IF geom_text IS NULL OR trim(geom_text) = '' THEN
            RETURN NULL;
        END IF;
        
        geom_text := trim(both '"' FROM trim(geom_text));
        
        -- Check for GeoJSON (starts with {)
        IF left(geom_text, 1) = '{' THEN
            result := ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(geom_text), 4326), 3857);
            RETURN result;
        END IF;
        
        -- Check for EWKT (starts with SRID=)
        IF upper(left(geom_text, 5)) = 'SRID=' THEN
            srid_part := split_part(geom_text, ';', 1);
            wkt_part := split_part(geom_text, ';', 2);
            extracted_srid := substring(srid_part from 6)::int;
            
            IF extracted_srid = 3857 THEN
                result := ST_GeomFromEWKT(geom_text);
            ELSE
                result := ST_Transform(ST_GeomFromEWKT(geom_text), 3857);
            END IF;
            RETURN result;
        END IF;
        
        -- Assume plain WKT in 3857 (no transform needed)
        result := ST_SetSRID(ST_GeomFromText(geom_text), 3857);
        RETURN result;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # ========================================================================
    # 5. ACL COMPILER FUNCTION (SRID 3857 with Transform)
    # ========================================================================
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
        ELSE
             rhs := quote_literal(val_text);
        END IF;

        -- Step 5: Operator & Casting Logic
        
        -- SPATIAL OPERATORS (SRID 3857 with Transform from 4326)
        IF op IN ('st_dwithin', 'st_contains', 'st_within', 'st_intersects', 'st_covers') THEN
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

    # ========================================================================
    # 5. ACL COMPILER TRIGGER
    # ========================================================================
    op.execute("""
    CREATE OR REPLACE FUNCTION trg_compile_acl_conditions_func()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.conditions IS NULL OR NEW.conditions::text = 'null' THEN
            NEW.compiled_sql := 'TRUE';
        ELSE
            NEW.compiled_sql := compile_condition_to_sql(NEW.conditions, 'p_ctx');
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER trg_compile_acl_conditions
    BEFORE INSERT OR UPDATE ON acl
    FOR EACH ROW
    EXECUTE FUNCTION trg_compile_acl_conditions_func();
    """)

    # ========================================================================
    # 6. AUTHORIZATION RUNNER (with Public Floodgate)
    # ========================================================================
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
        v_is_public BOOLEAN;
        rec RECORD;
    BEGIN
        -- Level 1: Floodgate (Public Flag)
        SELECT rt.is_public INTO v_is_public 
        FROM resource_type rt
        WHERE rt.id = p_resource_type_id;
        
        IF v_is_public THEN
            -- Fast Path: Return ALL resources of this type
            RETURN QUERY SELECT resource.id FROM resource WHERE resource.realm_id = p_realm_id AND resource.resource_type_id = p_resource_type_id;
            RETURN;
        END IF;

        -- Loop through matching ACLs
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
            
            -- Construct Query
            v_acl_sql := format(
                'SELECT resource.id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND (%s)',
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


def downgrade() -> None:
    """Drop all schema objects."""
    # Functions
    op.execute("DROP FUNCTION IF EXISTS get_authorized_resources CASCADE")
    op.execute("DROP TRIGGER IF EXISTS trg_compile_acl_conditions ON acl")
    op.execute("DROP FUNCTION IF EXISTS trg_compile_acl_conditions_func CASCADE")
    op.execute("DROP FUNCTION IF EXISTS compile_condition_to_sql CASCADE")
    
    # Partitioned Tables
    op.execute("DROP TABLE IF EXISTS external_ids CASCADE")
    op.execute("DROP TABLE IF EXISTS acl CASCADE")
    op.execute("DROP SEQUENCE IF EXISTS acl_id_seq")
    op.execute("DROP TABLE IF EXISTS resource CASCADE")
    
    # Regular Tables
    op.drop_table('realm_keycloak_config')
    op.drop_table('authorization_log')
    op.drop_table('principal_roles')
    op.drop_table('auth_role')
    op.drop_table('principal')
    op.drop_table('action')
    op.drop_index(op.f('ix_resource_type_is_public'), table_name='resource_type')
    op.drop_table('resource_type')
    op.drop_table('realm')
