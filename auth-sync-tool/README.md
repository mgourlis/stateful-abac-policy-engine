# Stateful ABAC Policy Engine Sync Tool

A CLI tool that generates [Stateful ABAC Policy Engine](../README.md) manifest files from external PostgreSQL databases using configurable YAML files.

## Features

- **Database Integration**: Fetch roles, principals, and resources from PostgreSQL
- **Keycloak Support**: Optional Keycloak configuration for authentication
- **Flexible ACLs**: Define access control at type-level or per-resource
- **Advanced Conditions**: Support for ABAC with nested AND/OR conditions and spatial operators
- **Environment Variables**: Secure credential handling with `${VAR}` syntax
- **Schema Validation**: JSON Schema for IDE autocompletion and validation

## Installation

### From GitHub

```bash
pip install git+https://github.com/enomix-gr/stateful-abac-policy-engine.git#subdirectory=auth-sync-tool
```

Or clone and install:

```bash
git clone https://github.com/enomix-gr/stateful-abac-policy-engine.git
cd stateful-abac-policy-engine/auth-sync-tool
pip install .
```

### From Source (Local Development)

```bash
cd auth-sync-tool
pip install -e .
```

### With Poetry (Development)

```bash
cd auth-sync-tool
poetry install
```

## Quick Start

1. **Create a configuration file** (see [config.example.yaml](config.example.yaml)):

```yaml
database:
  host: localhost
  database: my_app
  user: app_user
  password: "${DB_PASSWORD}"

realm:
  name: MyAppRealm

actions:
  - view
  - edit

resource_types:
  - name: document
    acls:
      - action: view
        role: reader
```

2. **Validate your configuration**:

```bash
stateful-abac-sync validate -c config.yaml
```

3. **Generate manifest**:

```bash
stateful-abac-sync generate -c config.yaml -o manifest.json
```

## CLI Commands

### `generate`

Generate a manifest.json from database sources.

```bash
stateful-abac-sync generate -c config.yaml -o manifest.json
stateful-abac-sync generate -c config.yaml --stdout          # Output to console
stateful-abac-sync generate -c config.yaml --indent 4        # Custom indentation
```

| Option | Description |
|--------|-------------|
| `-c, --config` | Path to YAML configuration file (required) |
| `-o, --output` | Output file path (default: `manifest.json`) |
| `--stdout` | Print to stdout instead of file |
| `--indent` | JSON indentation level (default: 2) |

### `validate`

Validate configuration file without connecting to database.

```bash
stateful-abac-sync validate -c config.yaml
```

## Configuration Reference

### Schema

Add to your YAML for IDE autocompletion:
```yaml
# yaml-language-server: $schema=config.schema.json
```

### Database

```yaml
database:
  type: postgresql        # Only PostgreSQL supported
  host: localhost
  port: 5432
  database: mydb
  user: myuser
  password: "${DB_PASSWORD}"  # Environment variable
```

### Realm

```yaml
realm:
  name: MyRealm
  description: "My application realm"
  
  # Optional Keycloak integration
  keycloak_config:
    server_url: "https://sso.example.com"
    keycloak_realm: "my-app"
    client_id: "demo-auth-client"
    client_secret: "${KC_SECRET}"
    sync_groups: true           # Skip roles/principals queries
    sync_cron: "0 */6 * * *"
    public_key: "${KC_PUBLIC_KEY}"
    algorithm: "RS256"
```

### Roles Query

Fetch roles from database (skipped if `sync_groups: true`):

```yaml
roles:
  query: |
    SELECT name, metadata::jsonb as attributes
    FROM app_roles WHERE active = true
  mappings:
    name: name
    attributes: attributes
```

### Principals Query

Fetch users with roles (skipped if Keycloak config exists):

```yaml
principals:
  query: |
    SELECT 
      u.username,
      u.profile::jsonb as attributes,
      ARRAY_AGG(r.name) as roles
    FROM users u
    LEFT JOIN user_roles ur ON u.id = ur.user_id
    LEFT JOIN roles r ON ur.role_id = r.id
    GROUP BY u.id
  mappings:
    username: username
    attributes: attributes
    roles: roles
```

### Resource Types

#### Basic with Type-Level ACLs

```yaml
resource_types:
  - name: document
    is_public: false
    acls:
      - action: view
        role: reader
      - action: edit
        role: editor
```

#### With Database Query

```yaml
resource_types:
  - name: document
    resources:
      query: |
        SELECT 
          id::text as external_id,
          jsonb_build_object('title', title) as attributes,
          ST_AsGeoJSON(location)::json as geometry
        FROM documents
      mappings:
        external_id: external_id
        attributes: attributes
        geometry: geometry
        srid: 4326
```

#### With Manual Resource List and Per-Resource ACLs

```yaml
resource_types:
  - name: facility
    resource_list:
      - external_id: "FAC-001"
        attributes:
          name: "Headquarters"
          status: active
        geometry:
          type: Point
          coordinates: [23.72, 37.98]
        acls:
          - action: enter
            role: admin
          - action: view
            principal_id: 0  # Anonymous access
```

### ACL Conditions

#### YAML Style: Flow vs Block

You can mix **Flow Style** `{ ... }` and **Block Style** anywhere in your configuration.
- **Flow Style**: Best for simple, one-line entries.
- **Block Style**: Essential for complex entries with nested properties (like conditions).

```yaml
acls:
  # Simple Entry (Flow Style)
  - { action: view, role: reader }

  # Complex Entry (Block Style)
  - action: edit
    role: editor
    conditions:
      op: "="
      attr: status
      val: draft
```


#### Simple Condition

```yaml
acls:
  - action: view
    role: viewer
    conditions:
      op: "="
      attr: status
      source: resource
      val: published
```

#### Nested AND/OR

```yaml
acls:
  - action: view
    role: agent
    conditions:
      op: or
      conditions:
        - op: "="
          attr: classification
          val: public
        - op: and
          conditions:
            - op: "="
              attr: region
              source: principal
              val: "$resource.attributes.region"
            - op: ">="
              attr: clearance
              source: principal
              val: 5
```

#### Spatial Conditions

```yaml
acls:
  - action: enter
    role: field_agent
    conditions:
      op: st_dwithin
      attr: geometry
      val: "$context.location"
      args: 1000  # meters
```

**Supported Operators**:
- Comparison: `=`, `!=`, `<`, `>`, `<=`, `>=`, `in`
- Logical: `and`, `or`
- Spatial: `st_dwithin`, `st_contains`, `st_within`, `st_intersects`, `st_covers`

**Variable References**:
- `$resource.attributes.<name>` - Resource attribute
- `$principal.attributes.<name>` - Principal attribute
- `$context.<name>` - Request context (e.g., location)

## Environment Variables

Use `${VAR_NAME}` syntax for sensitive values:

```yaml
database:
  password: "${DB_PASSWORD}"

realm:
  keycloak_config:
    client_secret: "${KC_SECRET}"
    public_key: "${KC_PUBLIC_KEY}"
```

## Output

The tool generates a JSON manifest compatible with the Stateful ABAC manifest schema.

Apply it using the SDK:

```python
from stateful_abac_sdk import StatefulABACClient

async def apply():
    client = StatefulABACClient(base_url="http://auth-service:8000/api/v1")
    await client.apply_manifest(manifest, mode="sync")
```

## Running Tests

```bash
pytest tests/ -v
```

## License

MIT
