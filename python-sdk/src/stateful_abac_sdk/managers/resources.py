from typing import List, Dict, Any, Optional, Union
from ..models import Resource
from .base import BaseManager
from ..interfaces import IResourceManager

class ResourceManager(BaseManager, IResourceManager):
    # Removed create_type and create_action as they now have dedicated managers.
        
    async def sync(self, resources: List[Resource]) -> Dict[str, Any]:
        """
        Sync resources using the batch endpoint.

        Args:
            resources: List of resource objects.

        Returns:
            The batch operation response.
        """
        # We will assume the user constructs the payload correctly for now, 
        # or we provide a helper to structure it?
        # Let's align with the API: method `batch_update`
        return await self.batch_update(create=resources)

    async def batch_update(self, 
                          create: Optional[List[Resource]] = None,
                          update: Optional[List[Resource]] = None,
                          delete: Optional[List[Any]] = None) -> Dict[str, Any]:
        """
        Perform batch operations on resources.

        Args:
            create: List of resources to create (must include external_id for later mapping).
            update: List of resources to update (match by external_id).
            delete: List of resources to delete (match by external_id).

        Returns:
            The API response dictionary.
        """
        realm_id = await self._resolve_realm_id()
        payload = {}
        if create: 
            payload["create"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in create]
        if update: 
            payload["update"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in update]
        if delete: 
            payload["delete"] = delete
        
        return await self._post(f"/realms/{realm_id}/resources/batch", json=payload)

    # Individual helpers
    async def create(self, 
                    resource_type_id: Optional[int] = None, 
                    external_id: Optional[str] = None, 
                    attributes: Optional[Dict[str, Any]] = None,
                    geometry: Optional[Union[Dict[str, Any], str]] = None,
                    srid: Optional[int] = None,
                    resource_type_name: Optional[str] = None) -> Resource:
        """
        Create a single resource.
        Supports resolution by Name OR ID.
        """
        realm_id = await self._resolve_realm_id()

        if resource_type_id is None and resource_type_name:
            resource_type_id = await self.client.lookup.get_id(realm_id, "resource_types", resource_type_name)
            
        if resource_type_id is None:
            raise ValueError("resource_type_id or resource_type_name required")

        data = {
            "resource_type_id": resource_type_id
        }
        if geometry: data["geometry"] = geometry
        if srid is not None: data["srid"] = srid
        if external_id: data["external_id"] = external_id
        if attributes: data["attributes"] = attributes
        
        response = await self._post(f"/realms/{realm_id}/resources", json=data)
        return Resource(**response)
        
    async def set_public(self, 
                        resource_id: int, 
                        resource_type_id: Optional[int] = None, 
                        action_id: Optional[int] = None, 
                        is_public: bool = True,
                        # Name-based
                        resource_type_name: Optional[str] = None,
                        action_name: Optional[str] = None) -> bool:
        """
        Make a specific resource public (Level 3) or private.
        Supports resolution by Name OR ID.
        """
        realm_id = await self._resolve_realm_id()
        
        if resource_type_id is None and resource_type_name:
            resource_type_id = await self.client.lookup.get_id(realm_id, "resource_types", resource_type_name)
            
        if action_id is None and action_name:
            action_id = await self.client.lookup.get_id(realm_id, "actions", action_name)
            
        if resource_type_id is None: raise ValueError("resource_type_id or resource_type_name required")
        if action_id is None: raise ValueError("action_id or action_name required")
        
        if is_public:
            await self.client.acls.create(
                resource_type_id=resource_type_id, 
                action_id=action_id, 
                principal_id=0, # 0 means public
                resource_id=resource_id,
                conditions={}
            )
        else:
            # Find and Delete Level 3 ACL Exception for Principal 0
            acls = await self.client.acls.list(
                resource_type_id=resource_type_id,
                action_id=action_id,
                principal_id=0,
                resource_id=resource_id
            )
            for acl in acls:
                if acl.id:
                    await self.client.acls.delete(acl.id)
                    
        return True
        
    async def get(self, resource_id: Union[int, str], resource_type: Optional[Union[int, str]] = None) -> Resource:
        """Get a resource (ID or External ID + Type)."""
        realm_id = await self._resolve_realm_id()
        if isinstance(resource_id, str):
             if not resource_type:
                  raise ValueError("resource_type (ID or Name) is required when using external_id")
             
             # Resolve resource_type if it's a name
             if isinstance(resource_type, str) and not resource_type.isdigit():
                  resource_type = await self.client.lookup.get_id(realm_id, "resource_types", resource_type)
             
             path = f"/realms/{realm_id}/resources/external/{resource_type}/{resource_id}"
             response = await self._get(path)
        else:
             response = await self._get(f"/realms/{realm_id}/resources/{resource_id}")
        return Resource(**response)

    async def update(self, resource_id: Union[int, str], 
                     resource_type: Optional[Union[int, str]] = None,
                     resource_type_id: Optional[int] = None, 
                     external_id: Optional[str] = None, 
                     attributes: Optional[Dict[str, Any]] = None,
                     geometry: Optional[Union[Dict[str, Any], str]] = None,
                     srid: Optional[int] = None) -> Resource:
        """Update a resource."""
        realm_id = await self._resolve_realm_id()
        data = {}
        if resource_type_id: data["resource_type_id"] = resource_type_id
        if external_id: data["external_id"] = external_id
        if attributes: data["attributes"] = attributes
        if geometry: data["geometry"] = geometry
        if srid is not None: data["srid"] = srid

        path = f"/realms/{realm_id}/resources/{resource_id}"
        if isinstance(resource_id, str):
             if not resource_type:
                  raise ValueError("resource_type (ID or Name) is required when using external_id")
             
             # Resolve resource_type if it's a name
             if isinstance(resource_type, str) and not resource_type.isdigit():
                  resource_type = await self.client.lookup.get_id(realm_id, "resource_types", resource_type)
             
             path = f"/realms/{realm_id}/resources/external/{resource_type}/{resource_id}"

        response = await self._put(path, json=data)
        return Resource(**response)

    async def delete(self, resource_id: Union[int, str], resource_type: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        """Delete a resource."""
        realm_id = await self._resolve_realm_id()
        path = f"/realms/{realm_id}/resources/{resource_id}"
        if isinstance(resource_id, str):
             if not resource_type:
                  raise ValueError("resource_type (ID or Name) is required when using external_id")
             
             # Resolve resource_type if it's a name
             if isinstance(resource_type, str) and not resource_type.isdigit():
                  resource_type = await self.client.lookup.get_id(realm_id, "resource_types", resource_type)
                  
             path = f"/realms/{realm_id}/resources/external/{resource_type}/{resource_id}"
        return await self._delete(path)

    async def list(self) -> List[Resource]:
        """List all resources (without pagination)."""
        realm_id = await self._resolve_realm_id()
        response = await self._get(f"/realms/{realm_id}/resources/all")
        return [Resource(**item) for item in response]

