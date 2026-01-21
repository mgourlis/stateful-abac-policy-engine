from typing import List, Dict, Any, Optional, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class BaseEntity(BaseModel):
    model_config = ConfigDict(extra='ignore')

class RealmKeycloakConfig(BaseEntity):
    server_url: str
    keycloak_realm: str
    client_id: str
    client_secret: Optional[str] = None
    verify_ssl: bool = True
    public_key: Optional[str] = None
    algorithm: str = "RS256"
    settings: Optional[Dict[str, Any]] = None
    sync_cron: Optional[str] = None
    sync_groups: bool = False

class Realm(BaseEntity):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool = True
    keycloak_config: Optional[RealmKeycloakConfig] = None

class ResourceType(BaseEntity):
    id: Optional[int] = None
    name: str
    is_public: bool = False
    realm_id: int

class Action(BaseEntity):
    id: Optional[int] = None
    name: str
    realm_id: int

class Role(BaseEntity):
    id: Optional[int] = None
    name: str
    attributes: Optional[Dict[str, Any]] = None
    realm_id: int

class Principal(BaseEntity):
    id: Optional[int] = None
    username: str
    attributes: Optional[Dict[str, Any]] = None
    realm_id: int
    roles: List[Role] = []
    role_ids: Optional[List[int]] = None

class Resource(BaseEntity):
    id: Optional[int] = None
    resource_type_id: Optional[int] = None
    external_id: Optional[Union[str, List[str]]] = None
    attributes: Optional[Dict[str, Any]] = None
    geometry: Optional[Union[Dict[str, Any], str]] = None
    srid: Optional[int] = None
    realm_id: int

class ACL(BaseEntity):
    id: Optional[int] = None
    realm_id: int
    resource_type_id: int
    resource_id: Optional[int] = None
    resource_external_id: Optional[str] = None
    action_id: int
    principal_id: Optional[int] = None
    role_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    compiled_sql: Optional[str] = None

class CheckAccessItem(BaseModel):
    resource_type_name: str
    action_name: str
    return_type: Literal["id_list", "decision"] = "id_list"
    external_resource_ids: Optional[Union[List[int], List[str]]] = None

class AccessResponseItem(BaseModel):
    """Response item for access check."""
    action_name: str
    resource_type_name: str
    answer: Union[bool, List[int], List[str]]

class AccessResponse(BaseModel):
    """Response container for access check."""
    results: List[AccessResponseItem]


# ============================================================================
# Get Permitted Actions - returns actions permitted per resource
# ============================================================================
class GetPermittedActionsItem(BaseModel):
    """Request item for get_permitted_actions."""
    resource_type_name: str
    external_resource_ids: Optional[List[str]] = None  # If None, type-level check


class PermittedActionsResponseItem(BaseModel):
    """Response item with permitted actions for a specific resource."""
    resource_type_name: str
    external_resource_id: Optional[str] = None  # None for type-level
    actions: List[str]  # List of permitted action names


class GetPermittedActionsResponse(BaseModel):
    """Response container for get_permitted_actions."""
    results: List[PermittedActionsResponseItem]
