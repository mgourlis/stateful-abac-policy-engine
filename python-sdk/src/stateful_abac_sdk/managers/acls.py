from typing import List, Dict, Any, Optional, Union
from ..models import ACL
from .base import BaseManager
from ..interfaces import IACLManager

class ACLManager(BaseManager, IACLManager):
    async def create(self, 
                    resource_type_id: Optional[int] = None,
                    action_id: Optional[int] = None,
                    principal_id: Optional[int] = None,
                    role_id: Optional[int] = None,
                    resource_id: Optional[int] = None,
                    resource_external_id: Optional[str] = None,
                    conditions: Optional[Dict[str, Any]] = None,
                    # Name-based alternatives
                    resource_type_name: Optional[str] = None,
                    action_name: Optional[str] = None,
                    principal_name: Optional[str] = None,
                    role_name: Optional[str] = None) -> ACL:
        """
        Create an ACL entry.
        Supports resolution by Name OR ID.
        """
        realm_id = await self._resolve_realm_id()

        # Resolve IDs if Names provided
        if resource_type_id is None and resource_type_name:
            resource_type_id = await self.client.lookup.get_id(realm_id, "resource_types", resource_type_name)
            
        if action_id is None and action_name:
            action_id = await self.client.lookup.get_id(realm_id, "actions", action_name)
            
        if principal_id is None and principal_name:
            principal_id = await self.client.lookup.get_id(realm_id, "principals", principal_name)
            
        if role_id is None and role_name:
            role_id = await self.client.lookup.get_id(realm_id, "roles", role_name)

        if resource_type_id is None: raise ValueError("resource_type_id or resource_type_name required")
        if action_id is None: raise ValueError("action_id or action_name required")

        data = {
            "realm_id": realm_id,
            "resource_type_id": resource_type_id,
            "action_id": action_id
        }
        
        # Handle mutual exclusion for DB constraint
        if role_id is not None and role_id != 0:
            data["role_id"] = role_id
            data["principal_id"] = None
        else:
            # Default case or if principal_id is specific (including 0 for public)
            data["principal_id"] = principal_id if principal_id is not None else 0
            data["role_id"] = None

        if resource_id is not None:
            data["resource_id"] = resource_id
        if resource_external_id is not None:
            data["resource_external_id"] = resource_external_id
        if conditions is not None:
            data["conditions"] = conditions
        
        response = await self._post(f"/realms/{realm_id}/acls", json=data)
        return ACL(**response)

    async def list(self, 
                  resource_type_id: Optional[int] = None,
                  action_id: Optional[int] = None,
                  principal_id: Optional[int] = None,
                  role_id: Optional[int] = None,
                  resource_id: Optional[int] = None,
                  # Name-based filtering
                  resource_type_name: Optional[str] = None,
                  action_name: Optional[str] = None,
                  principal_name: Optional[str] = None,
                  role_name: Optional[str] = None) -> List[ACL]:
        """
        List ACLs in a realm with optional filtering (ID or Name).
        """
        realm_id = await self._resolve_realm_id()
        
        # Resolve Names
        if resource_type_id is None and resource_type_name:
            resource_type_id = await self.client.lookup.get_id(realm_id, "resource_types", resource_type_name)
        if action_id is None and action_name:
            action_id = await self.client.lookup.get_id(realm_id, "actions", action_name)
        if principal_id is None and principal_name:
            principal_id = await self.client.lookup.get_id(realm_id, "principals", principal_name)
        if role_id is None and role_name:
            role_id = await self.client.lookup.get_id(realm_id, "roles", role_name)

        params = {}
        if resource_type_id is not None: params["resource_type_id"] = resource_type_id
        if action_id is not None: params["action_id"] = action_id
        if principal_id is not None: params["principal_id"] = principal_id
        if role_id is not None: params["role_id"] = role_id
        if resource_id is not None: params["resource_id"] = resource_id
        
        response = await self._get(f"/realms/{realm_id}/acls/all", params=params)
        return [ACL(**item) for item in response]

    async def get(self, acl_id: int) -> ACL:
        """Get an ACL."""
        realm_id = await self._resolve_realm_id()
        response = await self._get(f"/realms/{realm_id}/acls/{acl_id}")
        return ACL(**response)

    async def update(self, acl_id: int, conditions: Optional[Dict[str, Any]] = None) -> ACL:
        """Update an ACL."""
        realm_id = await self._resolve_realm_id()
        data = {}
        if conditions is not None:
             data["conditions"] = conditions
        
        response = await self._put(f"/realms/{realm_id}/acls/{acl_id}", json=data)
        return ACL(**response)

    async def delete(self, acl_id: int) -> Dict[str, Any]:
        """Delete an ACL."""
        realm_id = await self._resolve_realm_id()
        return await self._delete(f"/realms/{realm_id}/acls/{acl_id}")
    
    async def sync(self, acls: List[ACL]) -> Dict[str, Any]:
        """
        Sync ACLs (ensure they exist).

        Args:
            acls: List of ACL objects.

        Returns:
            Batch response.
        """
        return await self.batch_update(create=acls)

    async def batch_update(self, create: Optional[List[ACL]] = None,
                           update: Optional[List[ACL]] = None,
                           delete: Optional[List[Any]] = None) -> Dict[str, Any]:
        realm_id = await self._resolve_realm_id()
        payload = {}
        if create: 
            payload["create"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in create]
        if update: 
            payload["update"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in update]
        if delete: 
            payload["delete"] = delete
        return await self._post(f"/realms/{realm_id}/acls/batch", json=payload)
