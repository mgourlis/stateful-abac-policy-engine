from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from ..interfaces import (
    IRealmManager, IResourceManager, IPrincipalManager, IRoleManager,
    IActionManager, IResourceTypeManager, IACLManager, IAuthManager
)
try:
    from ..lookup import LookupService
except ImportError:
    LookupService = Any  # type: ignore

class IStatefulABACClient(ABC):
    """Interface for Stateful ABAC Client."""
    
    realms: IRealmManager
    resources: IResourceManager
    principals: IPrincipalManager
    roles: IRoleManager
    actions: IActionManager
    resource_types: IResourceTypeManager
    acls: IACLManager
    auth: IAuthManager
    lookup: Optional['LookupService']
    realm: str

    @abstractmethod
    def set_token(self, token: str):
        """Set the authentication token (mirrors HTTP client API)."""
        pass

    @abstractmethod
    def connect(self, token: str):
        """Context manager for connection."""
        pass

    @abstractmethod
    async def close(self):
        """Close connections."""
        pass

    @abstractmethod
    async def apply_manifest(self, path: str, mode: str = 'update') -> Dict[str, Any]:
        pass

    @abstractmethod
    async def export_manifest(self, realm_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        pass
