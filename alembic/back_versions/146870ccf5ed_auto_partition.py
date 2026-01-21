"""auto_partition

Revision ID: 146870ccf5ed
Revises: bcf4b510bd8b
Create Date: 2025-12-16 17:38:12.995932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '146870ccf5ed'
down_revision: Union[str, Sequence[str], None] = 'bcf4b510bd8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Function to create partitions
    op.execute("""
    CREATE OR REPLACE FUNCTION create_realm_partition_if_not_exists()
    RETURNS TRIGGER AS $$
    DECLARE
        v_realm_name TEXT;
        v_safe_name TEXT;
        v_partition_name_resource TEXT;
        v_partition_name_acl TEXT;
    BEGIN
        -- Fetch realm name
        SELECT name INTO v_realm_name FROM realm WHERE id = NEW.realm_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Realm with ID % not found', NEW.realm_id;
        END IF;

        -- Sanitize name
        v_safe_name := lower(regexp_replace(v_realm_name, '[^a-zA-Z0-9]', '_', 'g'));
        
        -- Resource Partition Check & Create
        -- We append realm_id to ensure uniqueness if names are reused (e.g. in tests)
        v_partition_name_resource := 'resource_' || v_safe_name || '_' || NEW.realm_id;
        IF to_regclass(v_partition_name_resource) IS NULL THEN
            RAISE NOTICE 'Creating partition % for realm %', v_partition_name_resource, NEW.realm_id;
            EXECUTE format('CREATE TABLE %I PARTITION OF resource FOR VALUES IN (%L)', v_partition_name_resource, NEW.realm_id);
        END IF;

        -- ACL Partition Check & Create
        v_partition_name_acl := 'acl_' || v_safe_name || '_' || NEW.realm_id;
        IF to_regclass(v_partition_name_acl) IS NULL THEN
            RAISE NOTICE 'Creating partition % for realm %', v_partition_name_acl, NEW.realm_id;
            EXECUTE format('CREATE TABLE %I PARTITION OF acl FOR VALUES IN (%L)', v_partition_name_acl, NEW.realm_id);
        END IF;

        -- For ACL, dynamic insert seems safer given previous issues, or maybe standard works now that naming is fixed?
        -- But I'll stick to dynamic insert to be robust against visibility issues.
        IF TG_TABLE_NAME = 'acl' THEN
            EXECUTE format('INSERT INTO %I VALUES ($1.*)', v_partition_name_acl) USING NEW;
            RETURN NULL;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # Triggers
    op.execute("""
    CREATE TRIGGER trg_auto_partition_resource
    BEFORE INSERT ON resource
    FOR EACH ROW
    EXECUTE FUNCTION create_realm_partition_if_not_exists();
    """)

    op.execute("""
    CREATE TRIGGER trg_auto_partition_acl
    BEFORE INSERT ON acl
    FOR EACH ROW
    EXECUTE FUNCTION create_realm_partition_if_not_exists();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_auto_partition_acl ON acl")
    op.execute("DROP TRIGGER IF EXISTS trg_auto_partition_resource ON resource")
    
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS create_realm_partition_if_not_exists")
