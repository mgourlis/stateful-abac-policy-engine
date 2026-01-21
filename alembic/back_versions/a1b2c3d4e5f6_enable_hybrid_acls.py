"""enable_hybrid_acls

Revision ID: a1b2c3d4e5f6
Revises: 1305ecc80b4d
Create Date: 2025-12-17 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '1305ecc80b4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Create Sequence
    op.execute("CREATE SEQUENCE IF NOT EXISTS acl_id_seq")

    # 2. Add 'id' column using the sequence
    # We use server_default to populate existing rows (if any)
    op.add_column('acl', sa.Column('id', sa.Integer(), nullable=False, server_default=sa.text("nextval('acl_id_seq'::regclass)")))
    
    # 3. Drop old Primary Key
    # Must use CASCADE to drop dependent PKs on partitions.
    op.execute("ALTER TABLE acl DROP CONSTRAINT IF EXISTS acl_pkey CASCADE")

    # 3b. Drop NOT NULL constraints on principal_id and role_id
    # (These were enforced by the old PK, but we want them nullable now due to Check constraint valid usage)
    op.execute("ALTER TABLE acl ALTER COLUMN principal_id DROP NOT NULL")
    op.execute("ALTER TABLE acl ALTER COLUMN role_id DROP NOT NULL")

    # 4. Add new Primary Key
    # Must include partition key (realm_id) AND sub-partition key (resource_type_id)
    op.execute("ALTER TABLE acl ADD PRIMARY KEY (realm_id, resource_type_id, id)")
    
    # 5. Add Functional Unique Index for Logic
    # (realm_id, resource_type_id, action_id, principal_id, role_id, COALESCE(resource_id, -1))
    op.execute("""
        CREATE UNIQUE INDEX idx_acl_unique_rule 
        ON acl (realm_id, resource_type_id, action_id, principal_id, role_id, COALESCE(resource_id, -1))
    """)

    # 6. Update get_authorized_resources to respect resource_id
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
        -- UPDATED: Now we select resource_id too
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
              )
        LOOP
            -- 1. Handle NULL or Empty SQL
            IF rec.compiled_sql IS NULL OR trim(rec.compiled_sql) = '' THEN
                v_final_sql := 'TRUE';
            ELSE
                v_final_sql := replace(rec.compiled_sql, 'p_ctx', '$1');
            END IF;
            
            -- 2. Handle Specific Resource ID (Hybrid Logic)
            IF rec.resource_id IS NOT NULL THEN
                -- If rule is for specific resource, AND the ID check
                v_final_sql := format('(%s) AND id = %L', v_final_sql, rec.resource_id);
            END IF;
            
            -- Construct Query
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

def downgrade() -> None:
    # Reverse
    op.execute("DROP INDEX IF EXISTS idx_acl_unique_rule")
    op.execute("ALTER TABLE acl DROP CONSTRAINT IF EXISTS acl_pkey CASCADE")
    
    # Restore Old PK (might be hard if data violates it? Assuming we don't for rollback)
    op.execute("""
        ALTER TABLE acl ADD PRIMARY KEY (realm_id, resource_type_id, action_id, principal_id, role_id)
    """)
    
    op.drop_column('acl', 'id')
    op.execute("DROP SEQUENCE IF EXISTS acl_id_seq")

    # Restore old function (without resource_id logic)
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
