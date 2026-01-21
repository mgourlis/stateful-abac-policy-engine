"""partitioned_tables

Revision ID: bcf4b510bd8b
Revises: 8d653be14d29
Create Date: 2025-12-16 17:37:12.995932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcf4b510bd8b'
down_revision: Union[str, Sequence[str], None] = '8d653be14d29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Resource Table
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

    # ACL Table
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


def downgrade() -> None:
    op.execute("DROP TABLE acl")
    op.execute("DROP TABLE resource")
