from typing import List, Dict, Any, Optional, Union
from ..models import Principal
from .base import BaseManager
from ..interfaces import IPrincipalManager

class PrincipalManager(BaseManager, IPrincipalManager):
    async def create(self, username: str, attributes: Optional[Dict[str, Any]] = None, roles: Optional[List[str]] = None) -> Principal:
        """
        Create a principal.

        Args:
            username: Username of the principal.
            attributes: Optional attributes dictionary.
            roles: Optional list of role names to assign.

        Returns:
            The created Principal object.
        """
        realm_id = await self._resolve_realm_id()
        data = {"username": username}
        if attributes:
            data["attributes"] = attributes
        if roles:
            data["roles"] = roles
            
        # Based on tests: POST /realms/{realm_id}/principals
        response = await self._post(f"/realms/{realm_id}/principals", json=data)
        self.client.lookup.invalidate(realm_id, "principals")
        return Principal(**response)

    async def list(self) -> List[Principal]:
        """
        List principals in a realm.

        Returns:
            List of Principal objects.
        """
        realm_id = await self._resolve_realm_id()
        response = await self._get(f"/realms/{realm_id}/principals")
        return [Principal(**item) for item in response]

    async def get(self, principal_id: Union[int, str]) -> Principal:
        """Get a principal."""
        realm_id = await self._resolve_realm_id()
        if isinstance(principal_id, str):
             principal_id = await self.client.lookup.get_id(realm_id, "principals", principal_id)
        
        response = await self._get(f"/realms/{realm_id}/principals/{principal_id}")
        return Principal(**response)

    async def update(self, principal_id: Union[int, str], username: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None, roles: Optional[List[str]] = None) -> Principal:
        """Update a principal."""
        realm_id = await self._resolve_realm_id()
        if isinstance(principal_id, str):
             principal_id = await self.client.lookup.get_id(realm_id, "principals", principal_id)
             
        data = {}
        if username: data["username"] = username
        if attributes: data["attributes"] = attributes
        if roles is not None: data["roles"] = roles
        
        response = await self._put(f"/realms/{realm_id}/principals/{principal_id}", json=data)
        self.client.lookup.invalidate(realm_id, "principals")
        return Principal(**response)

    async def delete(self, principal_id: Union[int, str]) -> Dict[str, Any]:
        """Delete a principal."""
        realm_id = await self._resolve_realm_id()
        if isinstance(principal_id, str):
             principal_id = await self.client.lookup.get_id(realm_id, "principals", principal_id)
             
        return await self._delete(f"/realms/{realm_id}/principals/{principal_id}")

    async def sync(self, principals: List[Principal]) -> Dict[str, Any]:
        """Sync principals."""
        return await self.batch_update(create=principals)
        
    async def batch_update(self, create: Optional[List[Principal]] = None, 
                           update: Optional[List[Principal]] = None, 
                           delete: Optional[List[Any]] = None) -> Dict[str, Any]:
        realm_id = await self._resolve_realm_id()
        payload = {}
        if create: 
             c_list = []
             for p in create:
                 d = p.model_dump(exclude_unset=True) if hasattr(p, 'model_dump') else p
                 # Handle roles conversion if p is a Principal object
                 if hasattr(p, 'roles') and p.roles:
                      # If roles are Role objects, extract names.
                      d["roles"] = [r.name if hasattr(r, 'name') else str(r) for r in p.roles]
                 c_list.append(d)
             payload["create"] = c_list

        if update: 
             u_list = []
             for p in update:
                 d = p.model_dump(exclude_unset=True) if hasattr(p, 'model_dump') else p
                 if hasattr(p, 'roles') and p.roles:
                      d["roles"] = [r.name if hasattr(r, 'name') else str(r) for r in p.roles]
                 u_list.append(d)
             payload["update"] = u_list

        if delete: 
            payload["delete"] = delete
            
        return await self._post(f"/realms/{realm_id}/principals/batch", json=payload)
