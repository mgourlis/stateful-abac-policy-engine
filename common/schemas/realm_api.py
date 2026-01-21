from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict

# --- Keycloak Config Schema ---
class RealmKeycloakConfigBase(BaseModel):
    server_url: str
    keycloak_realm: str
    client_id: str
    client_secret: Optional[str] = None
    verify_ssl: bool = True
    public_key: Optional[str] = None
    algorithm: str = "RS256"
    settings: Optional[Dict[str, Any]] = None
    
    # Sync settings (unix-cron string, e.g. "*/5 * * * *")
    sync_cron: Optional[str] = None
    sync_groups: bool = False

class RealmKeycloakConfigCreate(RealmKeycloakConfigBase):
    pass

class RealmKeycloakConfigUpdate(BaseModel):
    server_url: Optional[str] = None
    keycloak_realm: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    verify_ssl: Optional[bool] = None
    public_key: Optional[str] = None
    algorithm: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    sync_cron: Optional[str] = None
    sync_groups: Optional[bool] = None

class RealmKeycloakConfigRead(RealmKeycloakConfigBase):
    id: int
    realm_id: int
    model_config = ConfigDict(from_attributes=True)

# --- Realm Schemas ---
class RealmBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class RealmCreate(RealmBase):
    keycloak_config: Optional[RealmKeycloakConfigCreate] = None

class RealmUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    keycloak_config: Optional[RealmKeycloakConfigUpdate] = None

class RealmRead(RealmBase):
    id: int
    keycloak_config: Optional[RealmKeycloakConfigRead] = None
    model_config = ConfigDict(from_attributes=True)

# --- Role Schemas ---
class AuthRoleBase(BaseModel):
    name: str
    attributes: Optional[Dict[str, Any]] = None

class AuthRoleCreate(AuthRoleBase):
    pass

class AuthRoleUpdate(BaseModel):
    name: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

class AuthRoleRead(AuthRoleBase):
    id: int
    realm_id: int
    model_config = ConfigDict(from_attributes=True)

# --- Principal Schemas ---
class PrincipalBase(BaseModel):
    username: str
    attributes: Optional[Dict[str, Any]] = None

class PrincipalCreate(PrincipalBase):
    roles: Optional[List[str]] = None  # List of Role Names

class PrincipalUpdate(BaseModel):
    username: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    roles: Optional[List[str]] = None  # List of Role Names to Replace

class PrincipalRead(PrincipalBase):
    id: int
    realm_id: int
    roles: List[AuthRoleRead] = []
    model_config = ConfigDict(from_attributes=True)

# --- Batch Operations moved to end ---

# --- Action Schemas ---
class ActionBase(BaseModel):
    name: str

class ActionCreate(ActionBase):
    pass

class ActionUpdate(BaseModel):
    name: Optional[str] = None

class ActionRead(ActionBase):
    id: int
    realm_id: int
    model_config = ConfigDict(from_attributes=True)

# --- ResourceType Schemas ---
class ResourceTypeBase(BaseModel):
    name: str
    is_public: bool = False

class ResourceTypeCreate(ResourceTypeBase):
    pass

class ResourceTypeUpdate(BaseModel):
    name: Optional[str] = None
    is_public: Optional[bool] = None

class ResourceTypeRead(ResourceTypeBase):
    id: int
    realm_id: int
    model_config = ConfigDict(from_attributes=True)

# --- Resource Schemas ---
class ResourceBase(BaseModel):
    resource_type_id: int
    attributes: Optional[Dict[str, Any]] = None
    external_id: Optional[str] = None # Helper field, maps to ExternalID table

class ResourceCreate(ResourceBase):
    geometry: Optional[Union[Dict[str, Any], str]] = None # GeoJSON or EWKT string
    srid: Optional[int] = None

class ResourceUpdate(BaseModel):
    resource_type_id: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None
    external_id: Optional[str] = None
    geometry: Optional[Union[Dict[str, Any], str]] = None
    srid: Optional[int] = None

class ResourceRead(ResourceBase):
    id: int
    realm_id: int
    geometry: Optional[Union[Dict[str, Any], str]] = None
    external_id: Optional[Union[str, List[str]]] = None
    model_config = ConfigDict(from_attributes=True)

# --- ACL Schemas ---
class ACLBase(BaseModel):
    realm_id: int
    resource_id: Optional[int] = None
    action_id: int
    # One of role or principal
    role_id: Optional[int] = None
    principal_id: Optional[int] = None
    
    conditions: Optional[Dict[str, Any]] = None 
    # decision removed, ABAC uses conditions. If empty, defaults to TRUE (Allow all).

class ACLCreate(ACLBase):
    resource_type_id: int # Required for ACL table
    resource_external_id: Optional[str] = None # Helper to resolve resource_id

class ACLUpdate(BaseModel):
    conditions: Optional[Dict[str, Any]] = None

class ACLRead(ACLBase):
    id: int
    resource_type_id: int
    compiled_sql: Optional[str] = None
    decision: Optional[str] = None # Re-added for backward compatibility/display
    model_config = ConfigDict(from_attributes=True)

# --- Batch Operations ---
# --- Batch Schemas ---

# 1. Principal Batch Items
class PrincipalBatchUpdateItem(BaseModel):
    id: Optional[int] = None
    username: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

class BatchPrincipalOperation(BaseModel):
    create: List[PrincipalCreate] = []
    update: List[PrincipalBatchUpdateItem] = []
    delete: List[int] = []

# 2. Role Batch Items
class RoleBatchUpdateItem(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

class BatchRoleOperation(BaseModel):
    create: List[AuthRoleCreate] = []
    update: List[RoleBatchUpdateItem] = []
    delete: List[int] = []

# 3. Action Batch Items
class ActionBatchUpdateItem(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None

class BatchActionOperation(BaseModel):
    create: List[ActionCreate] = []
    update: List[ActionBatchUpdateItem] = []
    delete: List[int] = []

# 4. ResourceType Batch Items
class ResourceTypeBatchUpdateItem(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    is_public: Optional[bool] = None

class BatchResourceTypeOperation(BaseModel):
    create: List[ResourceTypeCreate] = []
    update: List[ResourceTypeBatchUpdateItem] = []
    delete: List[int] = []

# 5. Resource Batch Items
class ResourceBatchUpdateItem(BaseModel):
    id: Optional[int] = None
    external_id: Optional[str] = None
    
    # Update fields
    # Update fields
    resource_type_id: Optional[int] = None # Can be used to switch type or identifying? Usually update body.
    attributes: Optional[Dict[str, Any]] = None
    geometry: Optional[Union[Dict[str, Any], str]] = None

    # Helper validation?
    # Must have id OR external_id (and optionally resource_type_id for old style, but we made it optional/ambiguous check)
    
class ResourceBatchDeleteItem(BaseModel):
    id: Optional[int] = None
    external_id: Optional[str] = None
    resource_type_id: Optional[int] = None # Optional, for strict scoping if desired

class BatchResourceOperation(BaseModel):
    create: List[ResourceCreate] = []
    update: List[ResourceBatchUpdateItem] = []
    # Delete can be IDs or objects
    delete: List[Union[int, ResourceBatchDeleteItem]] = []

# 6. ACL Batch Items
class ACLBatchUpdateItem(BaseModel):
    # Keys to identify
    resource_type_id: int
    action_id: int
    principal_id: Optional[int] = None
    role_id: Optional[int] = None
    resource_id: Optional[int] = None
    resource_external_id: Optional[str] = None
    
    # Update fields
    conditions: Optional[Dict[str, Any]] = None

class ACLBatchDeleteItem(BaseModel):
    resource_type_id: int
    action_id: int
    principal_id: Optional[int] = None
    role_id: Optional[int] = None
    resource_id: Optional[int] = None
    resource_external_id: Optional[str] = None

class BatchACLOperation(BaseModel):
    create: List[ACLCreate] = []
    update: List[ACLBatchUpdateItem] = []
    delete: List[ACLBatchDeleteItem] = []
