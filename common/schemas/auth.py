from pydantic import BaseModel
from typing import List, Dict, Union, Literal, Any, Optional

class AccessRequestItem(BaseModel):
    action_name: str
    resource_type_name: str
    return_type: Literal['decision', 'id_list'] = 'id_list'
    external_resource_ids: Optional[List[str]] = None  # New

class CheckAccessRequest(BaseModel):
    realm_name: str
    role_names: Optional[List[str]] = None  # New: Active Roles Override
    req_access: List[AccessRequestItem]
    auth_context: Dict[str, Any] = {}

class AccessResponseItem(BaseModel):
    action_name: str
    resource_type_name: str
    answer: Union[List[int], List[str], bool]

class AccessResponse(BaseModel):
    results: List[AccessResponseItem]


# ============================================================================
# Get Permitted Actions - returns actions permitted per resource
# ============================================================================
class GetPermittedActionsItem(BaseModel):
    """Request item specifying a resource type and optional resource IDs."""
    resource_type_name: str
    external_resource_ids: Optional[List[str]] = None  # If None, type-level check


class GetPermittedActionsRequest(BaseModel):
    """Request to get permitted actions for resources."""
    realm_name: str
    role_names: Optional[List[str]] = None
    resources: List[GetPermittedActionsItem]
    auth_context: Dict[str, Any] = {}


class PermittedActionsResponseItem(BaseModel):
    """Response item with permitted actions for a specific resource."""
    resource_type_name: str
    external_resource_id: Optional[str] = None  # None for type-level
    actions: List[str]  # List of permitted action names


class GetPermittedActionsResponse(BaseModel):
    """Response containing permitted actions per resource."""
    results: List[PermittedActionsResponseItem]
