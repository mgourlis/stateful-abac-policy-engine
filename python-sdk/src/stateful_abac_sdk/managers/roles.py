from typing import List, Dict, Any, Optional, Union
from ..models import Role
from .base import BaseManager
from ..interfaces import IRoleManager

class RoleManager(BaseManager, IRoleManager):
    async def create(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Role:
        """
        Create a role.

        Args:
            name: Name of the role.
            attributes: Optional attributes dictionary.

        Returns:
            The created Role object.
        """
        realm_id = await self._resolve_realm_id()
        data = {"name": name}
        if attributes:
            data["attributes"] = attributes
        response = await self._post(f"/realms/{realm_id}/roles", json=data)
        self.client.lookup.invalidate(realm_id, "roles")
        return Role(**response)

    async def list(self) -> List[Role]:
        """
        List roles in a realm.

        Returns:
            List of Role objects.
        """
        realm_id = await self._resolve_realm_id()
        response = await self._get(f"/realms/{realm_id}/roles")
        return [Role(**item) for item in response]

    async def sync(self, roles: List[Role]) -> Dict[str, Any]:
        """
        Sync roles using batch endpoint.
        
        Args:
            roles: List of Role objects.

        Returns:
            Batch response.
        """
        return await self.batch_update(create=roles)

    async def batch_update(self, create: Optional[List[Role]] = None, 
                           update: Optional[List[Role]] = None, 
                           delete: Optional[List[Any]] = None) -> Dict[str, Any]:
        realm_id = await self._resolve_realm_id()
        payload = {}
        if create: 
            payload["create"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in create]
        if update: 
            payload["update"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in update]
        if delete: 
            payload["delete"] = delete
        return await self._post(f"/realms/{realm_id}/roles/batch", json=payload)

    async def get(self, role_id: Union[int, str]) -> Role:
        """
        Get a role.
        """
        realm_id = await self._resolve_realm_id()
        if isinstance(role_id, str):
             role_id = await self.client.lookup.get_id(realm_id, "roles", role_id)
             
        response = await self._get(f"/realms/{realm_id}/roles/{role_id}")
        return Role(**response)

    async def update(self, role_id: Union[int, str], name: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None) -> Role:
        """
        Update a role.
        """
        realm_id = await self._resolve_realm_id()
        if isinstance(role_id, str):
             role_id = await self.client.lookup.get_id(realm_id, "roles", role_id)
             
        data = {}
        if name: data["name"] = name
        if attributes: data["attributes"] = attributes
        
        response = await self._put(f"/realms/{realm_id}/roles/{role_id}", json=data)
        self.client.lookup.invalidate(realm_id, "roles")
        return Role(**response)

    async def delete(self, role_id: Union[int, str]) -> Dict[str, Any]:
        """
        Delete a role.
        """
        realm_id = await self._resolve_realm_id()
        if isinstance(role_id, str):
             role_id = await self.client.lookup.get_id(realm_id, "roles", role_id)
             
        return await self._delete(f"/realms/{realm_id}/roles/{role_id}")
