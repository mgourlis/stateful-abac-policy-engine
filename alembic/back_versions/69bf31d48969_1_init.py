"""1_init

Revision ID: 69bf31d48969
Revises: 
Create Date: 2025-12-16 22:57:57.355585

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '69bf31d48969'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable PostGIS Extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # 2. Create Base Identity Tables
    # Realm
    op.create_table(
        'realm',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Resource Type
    op.create_table(
        'resource_type',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', 'name')
    )

    # Action
    op.create_table(
        'action',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('realm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['realm_id'], ['realm.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('realm_id', 'name')
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
    op.create_index('ix_principal_attributes', 'principal', ['attributes'], unique=False, postgresql_using='gin')

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
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Create Partitioned Tables
    
    # Resource Table (Partitioned)
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

    # ACL Table (Partitioned)
    # Includes 'compiled_sql' column from the start
    op.execute("""
    CREATE TABLE acl (
        principal_id INT,
        role_id INT,
        realm_id INT NOT NULL,
        resource_type_id INT NOT NULL,
        resource_id INT,
        action_id INT NOT NULL,
        conditions JSONB,
        compiled_sql TEXT,
        CHECK (
            (principal_id IS NOT NULL AND role_id IS NULL) OR
            (principal_id IS NULL AND role_id IS NOT NULL)
        ),
        PRIMARY KEY (realm_id, resource_type_id, action_id, principal_id, role_id)
    ) PARTITION BY LIST (realm_id);
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

    # 4. Auto-Partition Triggers
    # op.execute("""
    # CREATE OR REPLACE FUNCTION create_realm_partition_if_not_exists()
    # RETURNS TRIGGER AS $$
    # DECLARE
    #     v_realm_name TEXT;
    #     v_safe_name TEXT;
    #     v_partition_name_resource TEXT;
    #     v_partition_name_acl TEXT;
    # BEGIN
    #     -- Fetch realm name
    #     SELECT name INTO v_realm_name FROM realm WHERE id = NEW.realm_id;
    #     IF NOT FOUND THEN
    #         RAISE EXCEPTION 'Realm with ID % not found', NEW.realm_id;
    #     END IF;

    #     -- Sanitize name
    #     v_safe_name := lower(regexp_replace(v_realm_name, '[^a-zA-Z0-9]', '_', 'g'));
        
    #     -- Resource Partition Check & Create
    #     v_partition_name_resource := 'resource_' || v_safe_name || '_' || NEW.realm_id;
    #     IF to_regclass(v_partition_name_resource) IS NULL THEN
    #         RAISE NOTICE 'Creating partition % for realm %', v_partition_name_resource, NEW.realm_id;
    #         EXECUTE format('CREATE TABLE %I PARTITION OF resource FOR VALUES IN (%L)', v_partition_name_resource, NEW.realm_id);
    #     END IF;

    #     -- ACL Partition Check & Create
    #     v_partition_name_acl := 'acl_' || v_safe_name || '_' || NEW.realm_id;
    #     IF to_regclass(v_partition_name_acl) IS NULL THEN
    #         RAISE NOTICE 'Creating partition % for realm %', v_partition_name_acl, NEW.realm_id;
    #         EXECUTE format('CREATE TABLE %I PARTITION OF acl FOR VALUES IN (%L)', v_partition_name_acl, NEW.realm_id);
    #     END IF;

    #     -- Dynamic insert to route data to partition
    #     IF TG_TABLE_NAME = 'acl' THEN
    #         EXECUTE format('INSERT INTO %I VALUES ($1.*)', v_partition_name_acl) USING NEW;
    #         RETURN NULL;
    #     END IF;

    #     RETURN NEW;
    # END;
    # $$ LANGUAGE plpgsql;
    # """)

    # op.execute("""
    # CREATE TRIGGER trg_auto_partition_resource
    # BEFORE INSERT ON resource
    # FOR EACH ROW
    # EXECUTE FUNCTION create_realm_partition_if_not_exists();
    # """)

    # op.execute("""
    # CREATE TRIGGER trg_auto_partition_acl
    # BEFORE INSERT ON acl
    # FOR EACH ROW
    # EXECUTE FUNCTION create_realm_partition_if_not_exists();
    # """)

    # 5. ACL Compiler Function (Latest Version with GeoJSON/EWKT)
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
        
        -- Path parsing variables
        raw_path TEXT;
        path_parts TEXT[];
        i INT;
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
        
        -- Step 4: RHS with NESTED PATH SUPPORT
        val_text := val #>> '{}';
        
        IF val_text LIKE '$%' THEN
             IF val_text LIKE '$principal.%' THEN
                 -- Extract "foo.bar" from "$principal.foo.bar"
                 raw_path := substr(val_text, 12);
                 path_parts := string_to_array(raw_path, '.');
                 
                 -- Start with context root
                 rhs := format('%s->''principal''', ctx_var);
                 
                 -- Iterate parts: ->'a'->'b'->>'c'
                 FOR i IN 1..array_length(path_parts, 1) LOOP
                    IF i = array_length(path_parts, 1) THEN
                        -- Last element uses ->> to return text
                        rhs := rhs || '->>' || quote_literal(path_parts[i]);
                    ELSE
                        -- Intermediate elements use -> to return jsonb
                        rhs := rhs || '->' || quote_literal(path_parts[i]);
                    END IF;
                 END LOOP;
                 
             ELSIF val_text LIKE '$context.%' THEN
                 -- Extract "ip.source" from "$context.ip.source"
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

    # 6. ACL Compiler Trigger
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

    op.execute("""
    CREATE TRIGGER trg_compile_acl_conditions
    BEFORE INSERT OR UPDATE ON acl
    FOR EACH ROW
    EXECUTE FUNCTION trg_compile_acl_conditions_func();
    """)

    # 7. Authorization Runner (Latest Version with Role Array)
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
        -- Loop through matching ACLs
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
            -- Replace placeholder with bind param
            v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            
            -- Construct Query
            v_acl_sql := format(
                'SELECT id FROM resource WHERE realm_id = %L AND resource_type_id = %L AND %s',
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
    # Reverse of upgrade
    op.execute("DROP FUNCTION IF EXISTS get_authorized_resources")
    op.execute("DROP TRIGGER IF EXISTS trg_compile_acl_conditions ON acl")
    op.execute("DROP FUNCTION IF EXISTS trg_compile_acl_conditions_func")
    op.execute("DROP FUNCTION IF EXISTS compile_condition_to_sql")
    # op.execute("DROP TRIGGER IF EXISTS trg_auto_partition_acl ON acl")
    # op.execute("DROP TRIGGER IF EXISTS trg_auto_partition_resource ON resource")
    # op.execute("DROP FUNCTION IF EXISTS create_realm_partition_if_not_exists")
    op.execute("DROP TABLE IF EXISTS external_ids CASCADE")
    op.execute("DROP TABLE IF EXISTS acl CASCADE")
    op.execute("DROP TABLE IF EXISTS resource CASCADE")
    op.drop_table('authorization_log')
    op.drop_table('principal_roles')
    op.drop_table('auth_role')
    op.drop_index('ix_principal_attributes', table_name='principal', postgresql_using='gin')
    op.drop_table('principal')
    op.drop_table('action')
    op.drop_table('resource_type')
    op.drop_table('realm')
