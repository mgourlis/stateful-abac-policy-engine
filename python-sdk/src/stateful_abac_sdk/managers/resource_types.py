from typing import List, Dict, Any, Optional, Union
from ..models import ResourceType
from .base import BaseManager
from ..interfaces import IResourceTypeManager

class ResourceTypeManager(BaseManager, IResourceTypeManager):
    async def create(self, name: str, is_public: bool = False, realm_id: Optional[Union[int, str]] = None) -> ResourceType:
        """
        Create a resource type.

        Args:
            name: The name of the resource type.
            is_public: Whether resources of this type are public by default.
            realm_id: Optional realm ID override.

        Returns:
            The created ResourceType.
        """
        if name is None:
             raise ValueError("name is required")
             
        realm_id = await self._resolve_realm_id(realm_id)
        json_data = {"name": name, "is_public": is_public}
        response = await self._post(f"/realms/{realm_id}/resource-types", json=json_data)
        self.client.lookup.invalidate(realm_id, "resource_types")
        return ResourceType(**response)

    async def list(self, realm_id: Optional[Union[int, str]] = None) -> List[ResourceType]:
        """
        List resource types in a realm.

        Args:
            realm_id: Optional realm ID override.

        Returns:
            List of ResourceType objects.
        """
        realm_id = await self._resolve_realm_id(realm_id)
        response = await self._get(f"/realms/{realm_id}/resource-types")
        return [ResourceType(**item) for item in response]

    async def sync(self, resource_types: List[ResourceType] = [], realm_id: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        """
        Sync resource types (ensure they exist).
        """
        return await self.batch_update(create=resource_types, realm_id=realm_id)

    async def batch_update(self, create: Optional[List[ResourceType]] = None,
                           update: Optional[List[ResourceType]] = None,
                           delete: Optional[List[Any]] = None,
                           realm_id: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        realm_id = await self._resolve_realm_id(realm_id)
        payload = {}
        if create: 
            payload["create"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in create]
        if update: 
            payload["update"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in update]
        if delete: 
            payload["delete"] = delete
        return await self._post(f"/realms/{realm_id}/resource-types/batch", json=payload)

    async def update(self, type_id: Union[int, str], name: Optional[str] = None, is_public: Optional[bool] = None, realm_id: Optional[Union[int, str]] = None) -> ResourceType:
        """
        Update a resource type.
        """
        if type_id is None:
             raise ValueError("type_id is required")

        realm_id = await self._resolve_realm_id(realm_id)
        if isinstance(type_id, str):
             type_id = await self.client.lookup.get_id(realm_id, "resource_types", type_id)
             
        data = {}
        if name is not None: data["name"] = name
        if is_public is not None: data["is_public"] = is_public
        
        response = await self._put(f"/realms/{realm_id}/resource-types/{type_id}", json=data)
        self.client.lookup.invalidate(realm_id, "resource_types")
        return ResourceType(**response)

    async def set_public(self, type_id: Union[int, str], is_public: bool = True, realm_id: Optional[Union[int, str]] = None) -> ResourceType:
        """
        Set the public status (Level 1 Floodgate) of a resource type.
        """
        return await self.update(type_id, is_public=is_public, realm_id=realm_id)

    async def get(self, type_id: Union[int, str], realm_id: Optional[Union[int, str]] = None) -> ResourceType:
        """
        Get a resource type.
        """
        if type_id is None:
             raise ValueError("type_id is required")

        realm_id = await self._resolve_realm_id(realm_id)
        if isinstance(type_id, str):
             type_id = await self.client.lookup.get_id(realm_id, "resource_types", type_id)
             
        response = await self._get(f"/realms/{realm_id}/resource-types/{type_id}")
        return ResourceType(**response)

    async def delete(self, type_id: Union[int, str], realm_id: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        """
        Delete a resource type.
        """
        if type_id is None:
             raise ValueError("type_id is required")

        realm_id = await self._resolve_realm_id(realm_id)
        if isinstance(type_id, str):
             type_id = await self.client.lookup.get_id(realm_id, "resource_types", type_id)
             
        return await self._delete(f"/realms/{realm_id}/resource-types/{type_id}")
