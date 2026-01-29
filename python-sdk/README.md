# Stateful ABAC Policy Engine Python SDK

Async Python client for the Stateful ABAC Policy Engine.

## Installation

```bash
# From PyPI (if published)
pip install stateful-abac-sdk

# From Source (Git) - HTTP mode only
pip install "stateful-abac-sdk @ git+https://github.com/enomix-gr/stateful-abac-policy-engine.git#subdirectory=python-sdk"

# From Source (Git) - With DB Mode support
# DB mode requires stateful-abac-common, install both:
pip install "stateful-abac-common @ git+https://github.com/enomix-gr/stateful-abac-policy-engine.git#subdirectory=common"
pip install "stateful-abac-sdk[db] @ git+https://github.com/enomix-gr/stateful-abac-policy-engine.git#subdirectory=python-sdk"

# From Local Path (Development)
pip install -e /path/to/stateful-abac-policy-engine/python-sdk

# From Local Path with DB Mode (Development)
pip install -e /path/to/stateful-abac-policy-engine/common
pip install -e /path/to/stateful-abac-policy-engine/python-sdk[db]
```

## Client Architecture

The SDK provides a **dual-mode client architecture** that supports both HTTP and direct database access, with a unified interface.

### Client Modes

| Mode | Class | Use Case | Performance |
|------|-------|----------|-------------|
| `http` | `HTTPStatefulABACClient` | Standard access via REST API | Good (network overhead) |
| `db` | `DBStatefulABACClient` | Direct database access for microservices | **10-100x faster** |

Both modes implement the `IStatefulABACClient` interface, ensuring identical API usage regardless of mode.

### Manager Interfaces

Each manager implements an abstract interface for API parity between modes:

| Interface | Purpose |
|-----------|---------|
| `IRealmManager` | Realm CRUD, Keycloak sync |
| `IResourceTypeManager` | Resource type definitions |
| `IActionManager` | Action definitions |
| `IRoleManager` | RBAC role management |
| `IPrincipalManager` | User/principal management |
| `IResourceManager` | Resource CRUD with geometry |
| `IACLManager` | Access control list management |
| `IAuthManager` | Authorization checks |

### Client Factory

Use `StatefulABACClientFactory` for flexible client creation:

```python
from stateful_abac_sdk.clients import StatefulABACClientFactory

# Create with explicit configuration
client = StatefulABACClientFactory.create(
    mode="http",
    realm="my_realm",
    base_url="http://localhost:8000/api/v1"
)

# Create from environment variables
# Uses STATEFUL_ABAC_CLIENT_MODE, STATEFUL_ABAC_CLIENT_BASE_URL, STATEFUL_ABAC_REALM
client = StatefulABACClientFactory.from_env()
```

### Convenience Function

`StatefulABACClient` is a convenience function that wraps the factory:

```python
from stateful_abac_sdk import StatefulABACClient

# HTTP mode - pass URL as first positional arg or base_url kwarg
client = StatefulABACClient("http://localhost:8000/api/v1", realm="my_realm")
# or
client = StatefulABACClient(base_url="http://localhost:8000/api/v1", realm="my_realm")

# DB mode - uses STATEFUL_ABAC_DATABASE_URL env var
client = StatefulABACClient(mode="db", realm="my_realm")
```

## Getting Started

### HTTP Mode (Default)

The SDK uses a **single realm scope** - you specify the realm once when creating the client, and all operations work within that realm context.

```python
import asyncio
from stateful_abac_sdk import StatefulABACClient

async def main():
    # Initialize the client with a realm
    client = StatefulABACClient(
        base_url="http://localhost:8000/api/v1",
        realm="my_realm"  # All operations scoped to this realm
    )
    
    async with client.connect(token="your-token"):
        # The realm is auto-provisioned if it doesn't exist!
        
        # No realm_id needed in manager calls
        types = await client.resource_types.list()
        actions = await client.actions.list()
        
        print(f"Connected to realm: {client.realm}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Auto-Provisioning

When you call `connect()`, the SDK automatically:
1. Checks if the realm exists
2. Creates it if not found
3. Configures Keycloak settings if provided via environment variables

```python
# Environment variables for auto-configured Keycloak
# STATEFUL_ABAC_KEYCLOAK_SERVER_URL=https://keycloak.example.com
# STATEFUL_ABAC_KEYCLOAK_REALM=my-kc-realm
# STATEFUL_ABAC_KEYCLOAK_CLIENT_ID=my-client
# STATEFUL_ABAC_KEYCLOAK_CLIENT_SECRET=secret

client = StatefulABACClient(
    base_url="http://localhost:8000/api/v1",
    realm="my_realm"  # Will be auto-created with Keycloak config
)
```

### DB Mode (High-Performance Direct Database Access)

For services that have direct access to the Stateful ABAC database, DB mode provides **10-100x faster** authorization checks by bypassing HTTP overhead.

```python
import asyncio
from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import CheckAccessItem

async def main():
    # Initialize the client in DB mode with realm
    client = StatefulABACClient(
        mode="db",
        realm="my_realm",
        db_url="postgresql+asyncpg://user:pass@localhost:5432/demo_auth",
        db_pool_size=5,
        db_max_overflow=10
    )
    
    async with client.connect(token="your-token"):
        # Same API as HTTP mode - but much faster!
        result = await client.auth.check_access(
            resources=[
                CheckAccessItem(
                    resource_type_name="buildings",
                    action_name="read",
                    external_resource_ids=["id1", "id2", ...]  # Millions of IDs
                )
            ]
        )
        
        # CRUD operations work identically - no realm_id needed
        resource = await client.resources.create(
            resource_type_name="buildings",
            external_id="building_123"
        )
    
    # Always close when done
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

> **Note**: All operations shown below should be awaited inside the `async with client.connect(token="your-token"):` block.

---

## Configuration

The SDK can be configured via environment variables or constructor arguments.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| **SDK Client** | | |
| `STATEFUL_ABAC_CLIENT_MODE` | Client mode: `http` or `db` | `http` |
| `STATEFUL_ABAC_CLIENT_BASE_URL` | Base URL for HTTP mode | - |
| `STATEFUL_ABAC_REALM` | Default realm name for the client | - |
| **Keycloak (Auto-Provisioning)** | | |
| `STATEFUL_ABAC_KEYCLOAK_SERVER_URL` | Keycloak server URL | - |
| `STATEFUL_ABAC_KEYCLOAK_REALM` | Keycloak realm name | - |
| `STATEFUL_ABAC_KEYCLOAK_CLIENT_ID` | Keycloak client ID | - |
| `STATEFUL_ABAC_KEYCLOAK_CLIENT_SECRET` | Keycloak client secret | - |
| `STATEFUL_ABAC_KEYCLOAK_SYNC_CRON` | Cron expression for sync | - |
| `STATEFUL_ABAC_KEYCLOAK_SYNC_GROUPS` | Sync groups from Keycloak | `false` |
| `STATEFUL_ABAC_KEYCLOAK_VERIFY_SSL` | Verify Keycloak SSL | `true` |
| **Database (DB Mode)** | | |
| `STATEFUL_ABAC_DATABASE_URL` | PostgreSQL connection URL | - |
| `STATEFUL_ABAC_POSTGRES_POOL_SIZE` | Connection pool size | `50` |
| `STATEFUL_ABAC_POSTGRES_MAX_OVERFLOW` | Max overflow connections | `50` |
| `STATEFUL_ABAC_POSTGRES_POOL_RECYCLE` | Pool recycle timeout (seconds) | `300` |
| `STATEFUL_ABAC_POSTGRES_POOL_TIMEOUT` | Pool timeout (seconds) | `30` |
| `STATEFUL_ABAC_POSTGRES_POOL_PRE_PING` | Enable pre-ping health check | `true` |
| **Security** | | |
| `STATEFUL_ABAC_JWT_SECRET_KEY` | JWT signing key | `changeme` |
| `STATEFUL_ABAC_JWT_ALGORITHM` | JWT algorithm | `HS256` |
| **Other** | | |
| `STATEFUL_ABAC_REDIS_URL` | Redis URL for caching | `redis://localhost:6379` |
| `STATEFUL_ABAC_TESTING` | Enable test mode | `false` |
| `STATEFUL_ABAC_ENABLE_SCHEDULER` | Enable background scheduler | `true` |

### Example .env File

```bash
# Client Configuration
STATEFUL_ABAC_CLIENT_MODE=http
STATEFUL_ABAC_CLIENT_BASE_URL=http://localhost:8000/api/v1
STATEFUL_ABAC_REALM=demo-auth

# Keycloak Integration
STATEFUL_ABAC_KEYCLOAK_SERVER_URL=http://localhost:8080
STATEFUL_ABAC_KEYCLOAK_REALM=demo-auth
STATEFUL_ABAC_KEYCLOAK_CLIENT_ID=demo-auth-sync
STATEFUL_ABAC_KEYCLOAK_CLIENT_SECRET=your-secret-here

# Database (for DB mode)
STATEFUL_ABAC_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/demo_auth

# Security
STATEFUL_ABAC_JWT_SECRET_KEY=your-secret-jwt-key
```

---

## Manager Reference

### 1. Realm Management
Manage security domains (Realms). Note: When using a client-scoped realm, most calls work on the current realm implicitly.

```python
from stateful_abac_sdk.models import RealmKeycloakConfig

# Get the current realm (auto-provisioned on connect)
realm = await client.realms.get()
print(f"Connected to: {realm.name}")

# Update the current realm
await client.realms.update(description="Updated Description")

# Update with Keycloak Configuration
kc_config = RealmKeycloakConfig(
    server_url="https://keycloak.example.com",
    keycloak_realm="my-realm",
    client_id="my-client",
    client_secret="secret",
    verify_ssl=True
)
await client.realms.update(keycloak_config=kc_config)
```

### Keycloak Integration Setup
To sync users and roles from Keycloak, you must configure a **Service Account** client in your Keycloak Realm:

1.  **Create Client**:
    *   **Client ID**: e.g., `demo-auth-sync`
    *   **Access Type**: `confidential` (This generates a Client Secret).
    *   **Service Accounts Enabled**: `ON`.

2.  **Assign Permissions** (Service Account Roles tab):
    *   Select Client Roles: `realm-management`.
    *   Assign Roles: `view-users`, `view-realm`, `view-clients`, `query-groups`.

3.  **Use Credentials**:
    *   Copy the `Client Secret` from the Credentials tab.
    *   Use this `client_id` and `client_secret` in the `RealmKeycloakConfig`.

### 2. Resource Type Management
Define classifications for resources (e.g., Document, Zone). All operations use the client's realm.

```python
# Create Private Type (Default)
rt_priv = await client.resource_types.create("secrets", is_public=False)

# Create Public Type (Floodgate Level 1 Access)
# ALL resources of this type are accessible to everyone (including anonymous)
rt_pub = await client.resource_types.create("public_docs", is_public=True)

# List Types
types = await client.resource_types.list()
```

### 3. Action Management
Define operations (e.g., view, edit, delete).

```python
# Create Action
action = await client.actions.create("view")

# List Actions
actions = await client.actions.list()
```

### 4. Principal & Role Management
Manage users (Principals) and RBAC roles.

```python
# Create Role
role = await client.roles.create("editor", attributes={"dept": "content"})

# Create Principal
user = await client.principals.create("alice", attributes={"clearance": 5})

# List
roles = await client.roles.list()
users = await client.principals.list()
```

### 5. Resource Management
Manage the protected objects. Supports batch sync.

```python
from stateful_abac_sdk import Resource

# Create Single Resource
res = await client.resources.create(
    name="Secret Plan", 
    resource_type_id=rt_priv.id,
    external_id="doc-1",
    attributes={"status": "draft"},
    geometry="POINT(23.7275 37.9838)",
    srid=4326
)

# Batch Sync (Upsert)
# Efficiently creates or updates multiple resources
await client.resources.sync([
    Resource(external_id="doc-2", name="Memo", resource_type_id=rt_priv.id, geometry="POINT(0 0)", srid=4326),
    Resource(external_id="pub-1", name="Public Notice", resource_type_id=rt_pub.id)
])
```

### 6. ACL Management
Define Attribute-Based Access Control rules. All operations use the client's realm implicitly.

```python
# A. Type-Level Rule (Level 2: Pattern)
# Grant "editor" role access to ALL "secrets"
await client.acls.create(
    resource_type_id=rt_priv.id,
    action_id=action.id,
    role_id=role.id,
    resource_id=None  # Applies to ALL resources of this type
)

# B. Resource-Level Rule (Level 3: Exception)
# Grant "alice" access to SPECIFIC "doc-1"
await client.acls.create(
    resource_type_id=rt_priv.id,
    action_id=action.id,
    principal_id=user.id,
    resource_external_id="doc-1"  # Resolve by external ID
)

# C. Attribute Condition (ABAC)
# Grant access if resource.attributes['status'] == 'active'
await client.acls.create(
    resource_type_id=rt_priv.id,
    action_id=action.id,
    role_id=role.id,
    conditions={"source": "resource", "attr": "status", "op": "=", "val": "active"}
)

# D. Granular Public Access (Hybrid)
# Even if a Type is Private, you can make specific resources public by 
# assigning an ACL to Principal ID 0 (The anonymous identity).
await client.acls.create(
    resource_type_id=rt_priv.id,
    action_id=action.id,
    principal_id=0,  # 0 = Public/Anonymous
    resource_external_id="doc-2"  # Only this specific resource is now public
)

# E. Using Names Instead of IDs
# No IDs required - the SDK resolves names automatically!
await client.acls.create(
    resource_type_name="secrets",
    action_name="view",
    role_name="editor"
)
```

### 3-Level Public Access Model
The system uses a waterfall logic for public access:
1. **Level 1 (Floodgate)**: If `ResourceType.is_public=True`, **ALL** resources of that type are public. Zero database overhead.
2. **Level 2 (Pattern)**: If a `principal_id=0` ACL exists with `resource_id=None` (applies to whole type).
3. **Level 3 (Exception)**: If a `principal_id=0` ACL exists for a **specific** `resource_id`.

## Automation Helpers
The SDK provides convenience methods to toggle public access easily.

```python
# 1. Type-Level Automation (Level 1)
# Make the entire 'Documents' type public
await client.resource_types.set_public(rt_priv.id, is_public=True)

# 2. Resource-Level Automation (Level 3)
# Make a SINGLE resource public (creates a Level 3 exception rule)
await client.resources.set_public(
    resource_id=res.id, 
    resource_type_id=rt_priv.id, 
    action_id=action.id,
    is_public=True
)

# Make it Private (Removes the exception rule)
await client.resources.set_public(
    resource_id=res.id, 
    resource_type_id=rt_priv.id, 
    action_id=action.id, 
    is_public=False
)
```


### 7. Checking Access
Verify permissions using the `AuthManager`. The realm is implicitly from the client.

```python
from stateful_abac_sdk.models import CheckAccessItem

# 1. Check Access (Return Decision Boolean)
decision_resp = await client.auth.check_access(
    resources=[
        CheckAccessItem(
            resource_type_name="secrets",
            action_name="view",
            return_type="decision" # Returns True/False if any access exists
        )
    ]
)
print(f"Access Granted: {decision_resp.results[0].answer}")

# 2. Check Access (Return List of IDs)
# Useful for "List my documents" - filters internal IDs automatically
list_resp = await client.auth.check_access(
    resources=[
        CheckAccessItem(
            resource_type_name="secrets",
            action_name="view",
            return_type="id_list" # Returns list of authorized External IDs
        )
    ]
)
print(f"Authorized Docs: {list_resp.results[0].answer}")

# 3. Check Specific Resources
item_resp = await client.auth.check_access(
    resources=[
        CheckAccessItem(
            resource_type_name="secrets",
            action_name="view",
            return_type="decision",
            external_resource_ids=["doc-1", "doc-2"]
        )
    ]
)
```

### 8. Get Authorization Conditions (Single-Query Authorization)
For applications that need to combine authorization with existing database queries, use `get_authorization_conditions()` to retrieve authorization conditions as JSON DSL.

```python
from stateful_abac_sdk.models import AuthorizationConditionsResponse

# Get authorization conditions for a resource type + action
auth_result = await client.auth.get_authorization_conditions(
    resource_type_name="documents",
    action_name="read",
    auth_context={"department": "Engineering", "ip": "10.0.0.5"}
)

# Handle the three possible filter types
if auth_result.filter_type == "denied_all":
    # User has no access whatsoever
    print("Access denied")
    return []

elif auth_result.filter_type == "granted_all":
    # User has unconditional access - no auth filter needed
    print("Full access granted")
    results = await execute_query(user_search_query)

else:  # filter_type == "conditions"
    # Merge authorization conditions with user's query
    print(f"Applying conditions: {auth_result.conditions_dsl}")
    
    # Convert to SearchQuery and merge (using search_query_dsl library)
    from search_query_dsl import ABACConditionConverter
    auth_query = ABACConditionConverter.convert(auth_result.conditions_dsl)
    merged_query = user_search_query.merge(auth_query)
    results = await execute_query(merged_query)
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `filter_type` | str | `'granted_all'`, `'denied_all'`, or `'conditions'` |
| `conditions_dsl` | dict | JSON condition DSL (only when `filter_type='conditions'`) |
| `has_context_refs` | bool | Whether conditions originally had `$context.*`/`$principal.*` refs |

#### Condition Evaluation

The server automatically:
- **Resolves references**: `$principal.department` → `"Engineering"`
- **Evaluates conditions**: `source='principal'` and `source='context'` conditions are evaluated server-side
- **Simplifies logic**: Removes evaluated `true` from AND, `false` from OR
- **Short-circuits**: Returns `granted_all` or `denied_all` when all conditions are evaluable

Only `source='resource'` conditions remain in `conditions_dsl` for database-side evaluation.

#### With Role Override

```python
# Check access as a specific role
auth_result = await client.auth.get_authorization_conditions(
    resource_type_name="documents",
    action_name="read",
    role_names=["Manager"]  # Only check Manager role access
)
```

## Available Commands API Reference

Below is a summary of the available methods on the `StatefulABACClient` managers. **All operations use the client's realm implicitly** - no `realm_id` argument needed.

### `client.realms` (`RealmManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Create the realm (auto-called on connect) | `description`, `keycloak_config` | `Realm` |
| `update` | Update the current realm | `description`, `keycloak_config` | `Realm` |
| `get` | Get the current realm | - | `Realm` |
| `delete` | Delete the current realm | - | `Dict` |
| `sync` | Trigger Keycloak sync | - | `Dict` |

### `client.resource_types` (`ResourceTypeManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Define a Resource Type | `name`, `is_public` | `ResourceType` |
| `update` | Update a Resource Type | `type_id`, `name`, `is_public` | `ResourceType` |
| `set_public` | Toggle Public Access | `type_id`, `is_public` | `ResourceType` |
| `list` | List all types | - | `List[ResourceType]` |
| `get` | Get Type by ID or Name | `type_id` | `ResourceType` |
| `delete` | Delete a Type | `type_id` | `Dict` |
| `sync` | Batch ensure types exist | `resource_types` | `Dict` |

### `client.actions` (`ActionManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Define an Action | `name` | `Action` |
| `update` | Update an Action | `action_id`, `name` | `Action` |
| `list` | List all actions | - | `List[Action]` |
| `get` | Get Action | `action_id` | `Action` |
| `delete` | Delete an Action | `action_id` | `Dict` |
| `sync` | Batch ensure actions exist | `actions` | `Dict` |

### `client.roles` (`RoleManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Define an RBAC Role | `name`, `attributes` | `Role` |
| `update` | Update a Role | `role_id`, `name`, `attributes` | `Role` |
| `list` | List roles | - | `List[Role]` |
| `get` | Get Role | `role_id` | `Role` |
| `delete` | Delete a Role | `role_id` | `Dict` |
| `sync` | Batch ensure roles exist | `roles` | `Dict` |

### `client.principals` (`PrincipalManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Create a User/Principal | `username`, `attributes`, `roles` | `Principal` |
| `update` | Update a Principal | `principal_id`, `username`, `attributes`, `roles` | `Principal` |
| `list` | List principals | - | `List[Principal]` |
| `get` | Get Principal | `principal_id` | `Principal` |
| `delete` | Delete a Principal | `principal_id` | `Dict` |
| `sync` | Batch ensure principals exist | `principals` | `Dict` |

### `client.resources` (`ResourceManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Create a Resource | `resource_type_id`/`name`, `external_id`, `attributes`, `geometry`, `srid` | `Resource` |
| `update` | Update a Resource | `resource_id`/`external_id`, `attributes`, `geometry`, `srid` | `Resource` |
| `list` | List resources | - | `List[Resource]` |
| `get` | Get Resource | `resource_id`/`external_id`, `resource_type` | `Resource` |
| `delete` | Delete a Resource | `resource_id`/`external_id`, `resource_type` | `Dict` |
| `set_public` | Toggle Public Access | `resource_id`, `resource_type_id`, `action_id`, `is_public` | `bool` |
| `sync` | Batch Upsert Resources | `resources` | `Dict` |
| `batch_update`| Full Batch Control | `create`, `update`, `delete` | `Dict` |

### `client.acls` (`ACLManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `create` | Create a Rule | `resource_type_id`/`name`, `action_id`/`name`, `principal_id`/`role_id`, `conditions` | `ACL` |
| `list` | List ACLs | `resource_type_id`, `action_id`, `principal_id`, `role_id` | `List[ACL]` |
| `get` | Get ACL by ID | `acl_id` | `ACL` |
| `update` | Update ACL | `acl_id`, `conditions` | `ACL` |
| `delete` | Delete ACL | `acl_id` | `Dict` |
| `sync` | Batch ensure ACLs exist | `acls` | `Dict` |
| `batch_update`| Full Batch Control | `create`, `update`, `delete` | `Dict` |

### `client.auth` (`AuthManager`)
| Method | Description | Arguments | Returns |
|--------|-------------|-----------|---------|
| `check_access` | Verify Permissions | `resources`, `auth_context`, `role_names` | `AccessResponse` |
| `get_authorization_conditions` | Get auth conditions as DSL | `resource_type_name`, `action_name`, `auth_context`, `role_names` | `AuthorizationConditionsResponse` |

---

## Manifest Management

The SDK provides powerful manifest management for declarative realm configuration.

### Apply Manifest

Three application modes are available:

```python
# 1. Update Mode (Default - Upsert)
# Creates new entities, updates existing ones
await client.apply_manifest("manifest.json", mode='update')

# 2. Create Mode (Add Only)
# Skips entities that already exist
await client.apply_manifest("manifest.json", mode='create')

# 3. Replace Mode (Destructive)
# Deletes realm and recreates from scratch
await client.apply_manifest("manifest.json", mode='replace')
```

**Smart Upload**: Large manifests (>1MB) are automatically uploaded to the server for processing.

### Export Manifest

Export the current realm configuration as JSON:

```python
# Export to dictionary
manifest = await client.export_manifest("MyRealm")

# Export and save to file
manifest = await client.export_manifest("MyRealm", output_path="backup.json")
```

The exported manifest includes:
- Realm configuration and Keycloak settings
- Resource types, actions, roles, principals
- Resources with attributes and geometry
- ACLs with conditions

### Programmatic Construction (ManifestBuilder)

The `ManifestBuilder` provides a fluent interface to construct manifests programmatically, which is less error-prone than manual JSON editing.

```python
from stateful_abac_sdk import ManifestBuilder, ConditionBuilder

# 1. Initialize Builder
builder = ManifestBuilder("MyRealm", description="Programmatically created realm")

# 2. Configure Keycloak (Optional)
builder.set_keycloak_config(
    server_url="https://sso.example.com",
    keycloak_realm="apps",
    client_id="my-app"
)

# 3. Define Types, Actions, and Roles
builder.add_resource_type("document", is_public=False)
builder.add_action("view")
builder.add_action("edit")
builder.add_role("editor")

# 4. Add Principal with Fluent Configuration
builder.add_principal("alice") \
    .with_role("editor") \
    .with_attribute("dept", "engineering") \
    .end()

# 5. Add Resource with Fluent Configuration
builder.add_resource("doc-1", "document") \
    .with_attribute("classification", "confidential") \
    .with_geometry({"type": "Point", "coordinates": [23.7275, 37.9838]}, srid=4326) \
    .end()

# 6. Add ACL with Fluent Conditions
builder.add_acl("document", "view") \
    .for_role("editor") \
    .when(
        ConditionBuilder.and_(
            ConditionBuilder.attr("status").eq("active"),
            ConditionBuilder.attr("clearance").from_principal().gte(3)
        )
    ) \
    .end()

# 7. Build or Export
manifest_dict = builder.build()
json_str = builder.to_json(indent=2)
```

**FluentCondition API** (via `ConditionBuilder.attr(name)`):

| Method | Description | Example |
|--------|-------------|---------|
| `.from_principal()` | Source from principal | `.from_principal().gte(5)` |
| `.from_context()` | Source from context | `.from_context().gte(9)` |
| `.from_resource()` | Source from resource (default) | `.from_resource().eq("active")` |
| `.eq(val)` | Equal | `.eq("active")` |
| `.neq(val)` | Not equal | `.neq("deleted")` |
| `.gt(val)` | Greater than | `.gt(5)` |
| `.lt(val)` | Less than | `.lt(100)` |
| `.gte(val)` | Greater than or equal | `.gte(18)` |
| `.lte(val)` | Less than or equal | `.lte(65)` |
| `.is_in(list)` | Value in list | `.is_in(["a", "b"])` |
| `.not_in(list)` | Value NOT in list | `.not_in(["deleted", "archived"])` |
| `.all_(list)` | Array contains all values | `.all_(["admin", "moderator"])` |
| `.dwithin(geom, dist)` | Within distance (meters) | `.dwithin("$context.loc", 5000)` |
| `.contains(geom)` | Geometry contains | `.contains("$context.loc")` |
| `.within(geom)` | Within geometry | `.within("$context.zone")` |
| `.intersects(geom)` | Intersects geometry | `.intersects("$context.area")` |
| `.covers(geom)` | Covers geometry | `.covers("$context.point")` |

**Logical Operators** (static methods):
- `ConditionBuilder.and_(c1, c2, ...)` - Logical AND
- `ConditionBuilder.or_(c1, c2, ...)` - Logical OR
- `ConditionBuilder.not_(condition)` - Logical NOT (negates a single condition)

**NOT Operator Examples**:
```python
# Simple negation - grant access to non-deleted documents
ConditionBuilder.not_(
    ConditionBuilder.attr("deleted").eq(True)
)

# Compound negation - exclude your own drafts
ConditionBuilder.not_(
    ConditionBuilder.and_(
        ConditionBuilder.attr("status").eq("draft"),
        ConditionBuilder.attr("owner").eq("$principal.username")
    )
)

# Combine NOT with other operators
ConditionBuilder.and_(
    ConditionBuilder.not_(ConditionBuilder.attr("archived").eq(True)),
    ConditionBuilder.attr("status").not_in(["deleted", "hidden"])
)
```

**Helper Builders** (returned by `add_*` methods):

| Builder | Methods |
|---------|---------|
| `ManifestPrincipalBuilder` | `.with_role(name)`, `.with_attribute(key, val)`, `.end()` |
| `ManifestResourceBuilder` | `.with_attribute(key, val)`, `.with_geometry(geom, srid)`, `.end()` |
| `ACLBuilder` | `.for_role(name)`, `.for_principal(name)`, `.for_resource(id)`, `.when(cond)`, `.end()` |

---

## External ID Management

### Resource Type Scoping

When working with external IDs, you **must** specify the resource type to avoid ambiguity:

```python
# Get resource by external ID + type name
resource = await client.resources.get(
    "EXT-001",  # External ID
    resource_type="Document"  # Required for external IDs
)

# Update by external ID + type ID
await client.resources.update(
    "EXT-001",
    resource_type=123,  # Can use type ID
    attributes={"status": "active"}
)

# Delete by external ID + type name
await client.resources.delete(
    "EXT-001",
    resource_type="Document"
)
```

**Why scoping is required**: Multiple resources can share the same external ID if they belong to different resource types. The schema allows this by design: `PRIMARY KEY (realm_id, resource_type_id, external_id)`.

**Multiple IDs**: A single resource can have multiple External IDs (aliases). The SDK `Resource` model supports `external_id` as either a single string (input) or a list of strings (output).

---

## Anonymous Client
For checking public access (Level 1) or anonymous permissions.

```python
async with StatefulABACClient("http://localhost:8000/api/v1").connect(token=None) as anon:
    resp = await anon.auth.check_access(
        resources=[
            CheckAccessItem(resource_type_name="public_docs", action_name="view")
        ]
    )
    # Should be True for 'public_docs' type
```
