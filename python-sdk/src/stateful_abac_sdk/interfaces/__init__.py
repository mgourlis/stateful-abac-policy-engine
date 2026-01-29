"""
Abstract interfaces for SDK managers.
Both HTTP and DB managers implement these interfaces, ensuring API parity.
Signatures are taken from HTTP managers (source of truth).
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import (
        Realm, ResourceType, Action, Principal, Role, Resource, ACL,
        CheckAccessItem, RealmKeycloakConfig, GetPermittedActionsItem,
        GetPermittedActionsResponse, AuthorizationConditionsResponse
    )
    from .managers.auth import AccessResponse


# ============================================================================
# IRealmManager
# ============================================================================
class IRealmManager(ABC):
    """Interface for realm operations."""
    
    @abstractmethod
    async def create(
        self, 
        description: Optional[str] = None, 
        keycloak_config: Optional["RealmKeycloakConfig"] = None
    ) -> "Realm":
        """Create new realm."""
        pass
    
    @abstractmethod
    async def get(self) -> "Realm":
        """Get the current realm."""
        pass
    
    @abstractmethod
    async def update(
        self, 
        description: Optional[str] = None,
        keycloak_config: Optional["RealmKeycloakConfig"] = None,
    ) -> "Realm":
        """Update the current realm."""
        pass
    
    @abstractmethod
    async def delete(self) -> Dict[str, Any]:
        """Delete the current realm."""
        pass
    
    @abstractmethod
    async def sync(self) -> Dict[str, Any]:
        """Trigger Keycloak sync for the current realm."""
        pass


# ============================================================================
# IResourceTypeManager
# ============================================================================
class IResourceTypeManager(ABC):
    """Interface for resource type operations."""
    
    @abstractmethod
    async def create(
        self, 
        name: str, 
        is_public: bool = False
    ) -> "ResourceType":
        pass
    
    @abstractmethod
    async def list(self) -> List["ResourceType"]:
        pass
    
    @abstractmethod
    async def get(self, type_id: Union[int, str]) -> "ResourceType":
        pass
    
    @abstractmethod
    async def update(
        self, 
        type_id: Union[int, str],
        name: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> "ResourceType":
        pass
    
    @abstractmethod
    async def set_public(
        self, 
        type_id: Union[int, str], 
        is_public: bool = True
    ) -> "ResourceType":
        pass
    
    @abstractmethod
    async def delete(self, type_id: Union[int, str]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def sync(
        self,
        resource_types: List["ResourceType"]
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def batch_update(
        self,
        create: Optional[List["ResourceType"]] = None,
        update: Optional[List["ResourceType"]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass


# ============================================================================
# IActionManager
# ============================================================================
class IActionManager(ABC):
    """Interface for action operations."""
    
    @abstractmethod
    async def create(self, name: str) -> "Action":
        pass
    
    @abstractmethod
    async def list(self) -> List["Action"]:
        pass
    
    @abstractmethod
    async def get(self, action_id: Union[int, str]) -> "Action":
        pass
    
    @abstractmethod
    async def update(
        self, 
        action_id: Union[int, str],
        name: str
    ) -> "Action":
        pass
    
    @abstractmethod
    async def delete(self, action_id: Union[int, str]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def sync(
        self,
        actions: List["Action"]
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def batch_update(
        self,
        create: Optional[List["Action"]] = None,
        update: Optional[List["Action"]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass


# ============================================================================
# IPrincipalManager
# ============================================================================
class IPrincipalManager(ABC):
    """Interface for principal operations."""
    
    @abstractmethod
    async def create(
        self, 
        username: str,
        attributes: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None
    ) -> "Principal":
        pass
    
    @abstractmethod
    async def list(self) -> List["Principal"]:
        pass
    
    @abstractmethod
    async def get(self, principal_id: Union[int, str]) -> "Principal":
        pass
    
    @abstractmethod
    async def update(
        self, 
        principal_id: Union[int, str],
        username: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None
    ) -> "Principal":
        pass
    
    @abstractmethod
    async def delete(self, principal_id: Union[int, str]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def sync(
        self,
        principals: List["Principal"]
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def batch_update(
        self,
        create: Optional[List["Principal"]] = None,
        update: Optional[List["Principal"]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass


# ============================================================================
# IRoleManager
# ============================================================================
class IRoleManager(ABC):
    """Interface for role operations."""
    
    @abstractmethod
    async def create(
        self, 
        name: str,
        attributes: Optional[Dict[str, Any]] = None
    ) -> "Role":
        pass
    
    @abstractmethod
    async def list(self) -> List["Role"]:
        pass
    
    @abstractmethod
    async def get(self, role_id: Union[int, str]) -> "Role":
        pass
    
    @abstractmethod
    async def update(
        self, 
        role_id: Union[int, str],
        name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> "Role":
        pass
    
    @abstractmethod
    async def delete(self, role_id: Union[int, str]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def sync(
        self,
        roles: List["Role"]
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def batch_update(
        self,
        create: Optional[List["Role"]] = None,
        update: Optional[List["Role"]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass


# ============================================================================
# IResourceManager
# ============================================================================
class IResourceManager(ABC):
    """Interface for resource operations."""
    
    @abstractmethod
    async def create(
        self, 
        resource_type_id: Optional[int] = None,
        external_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        geometry: Optional[Union[Dict[str, Any], str]] = None,
        srid: Optional[int] = None,
        resource_type_name: Optional[str] = None
    ) -> "Resource":
        pass
    
    @abstractmethod
    async def list(self) -> List["Resource"]:
        pass
    
    @abstractmethod
    async def get(
        self, 
        resource_id: Optional[Union[int, str]] = None,
        resource_type: Optional[Union[int, str]] = None
    ) -> "Resource":
        pass
    
    @abstractmethod
    async def update(
        self, 
        resource_id: Optional[Union[int, str]] = None,
        resource_type: Optional[Union[int, str]] = None,
        resource_type_id: Optional[int] = None,
        external_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        geometry: Optional[Union[Dict[str, Any], str]] = None,
        srid: Optional[int] = None
    ) -> "Resource":
        pass
    
    @abstractmethod
    async def delete(
        self, 
        resource_id: Optional[Union[int, str]] = None,
        resource_type: Optional[Union[int, str]] = None
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def set_public(
        self, 
        resource_id: int,
        resource_type_id: Optional[int] = None,
        action_id: Optional[int] = None,
        is_public: bool = True,
        resource_type_name: Optional[str] = None,
        action_name: Optional[str] = None
    ) -> bool:
        pass
    
    @abstractmethod
    async def sync(self, resources: List["Resource"]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def batch_update(
        self,
        create: Optional[List["Resource"]] = None,
        update: Optional[List["Resource"]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass


# ============================================================================
# IACLManager
# ============================================================================
class IACLManager(ABC):
    """Interface for ACL operations."""
    
    @abstractmethod
    async def create(
        self, 
        resource_type_id: Optional[int] = None,
        action_id: Optional[int] = None,
        principal_id: Optional[int] = None,
        role_id: Optional[int] = None,
        resource_id: Optional[int] = None,
        resource_external_id: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None,
        resource_type_name: Optional[str] = None,
        action_name: Optional[str] = None,
        principal_name: Optional[str] = None,
        role_name: Optional[str] = None
    ) -> "ACL":
        pass
    
    @abstractmethod
    async def list(
        self, 
        resource_type_id: Optional[int] = None,
        action_id: Optional[int] = None,
        principal_id: Optional[int] = None,
        role_id: Optional[int] = None,
        resource_id: Optional[int] = None,
        resource_type_name: Optional[str] = None,
        action_name: Optional[str] = None,
        principal_name: Optional[str] = None,
        role_name: Optional[str] = None
    ) -> List["ACL"]:
        pass
    
    @abstractmethod
    async def get(self, acl_id: Optional[int] = None) -> "ACL":
        pass
    
    @abstractmethod
    async def update(
        self, 
        acl_id: Optional[int] = None,
        conditions: Optional[Dict[str, Any]] = None
    ) -> "ACL":
        pass
    
    @abstractmethod
    async def delete(self, acl_id: Optional[int] = None) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def sync(self, acls: List["ACL"]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def batch_update(
        self,
        create: Optional[List["ACL"]] = None,
        update: Optional[List["ACL"]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass


# ============================================================================
# IAuthManager
# ============================================================================
class IAuthManager(ABC):
    """Interface for authorization checks."""
    
    @abstractmethod
    async def check_access(
        self, 
        resources: List["CheckAccessItem"],
        auth_context: Optional[Dict[str, Any]] = None,
        role_names: Optional[List[str]] = None,
        chunk_size: Optional[int] = None,
        max_concurrent: Optional[int] = None
    ) -> "AccessResponse":
        """
        Check access for a list of resources.
        
        Args:
            resources: List of CheckAccessItem objects.
            auth_context: Optional context dictionary for condition evaluation.
            role_names: Optional list of role names to check against.
            chunk_size: Optional override for chunk size (HTTP mode).
            max_concurrent: Optional override for max concurrent requests (HTTP mode).
            
        Returns:
            AccessResponse with results for each resource type/action pair.
        """
        pass

    @abstractmethod
    async def get_permitted_actions(
        self,
        resources: List["GetPermittedActionsItem"],
        auth_context: Optional[Dict[str, Any]] = None,
        role_names: Optional[List[str]] = None
    ) -> "GetPermittedActionsResponse":
        """
        Get the list of permitted actions for each resource.
        
        Args:
            resources: List of GetPermittedActionsItem objects.
            auth_context: Optional context dictionary for condition evaluation.
            role_names: Optional list of role names to check against.
            
        Returns:
            GetPermittedActionsResponse with actions permitted per resource.
        """
        pass

    @abstractmethod
    async def get_authorization_conditions(
        self,
        resource_type_name: str,
        action_name: str,
        auth_context: Optional[Dict[str, Any]] = None,
        role_names: Optional[List[str]] = None
    ) -> "AuthorizationConditionsResponse":
        """
        Get authorization conditions as JSON DSL for SearchQuery conversion.
        
        This enables single-query authorization: the returned conditions can be
        converted to a SearchQuery using ABACConditionConverter and merged with
        user queries using SearchQuery.merge() for optimal database performance.
        
        Context references ($context.* and $principal.*) are resolved server-side
        before returning, so the conditions_dsl is ready for direct conversion.
        
        Args:
            resource_type_name: Name of the resource type.
            action_name: Action being performed (e.g., "read", "update").
            auth_context: Optional runtime context for $context.* resolution.
            role_names: Optional list of role names to check against.
            
        Returns:
            AuthorizationConditionsResponse with:
                - filter_type: 'granted_all', 'denied_all', or 'conditions'
                - conditions_dsl: JSON condition DSL with resolved context references
                - external_ids: List of specifically granted resource external IDs
                - has_context_refs: Whether conditions originally had context references
        """
        pass
