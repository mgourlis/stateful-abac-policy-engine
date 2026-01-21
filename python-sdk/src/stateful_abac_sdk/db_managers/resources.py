"""
DB Manager for ResourceModel operations.
"""
from typing import List, Dict, Any, Optional, Union
from .base import DBBaseManager
from ..models import Resource
from ..interfaces import IResourceManager
from common.application.resource_service import ResourceService
from common.schemas.realm_api import ResourceCreate, ResourceUpdate, BatchResourceOperation


class DBResourceManager(DBBaseManager, IResourceManager):
    """DB-mode manager for resource operations."""
    
    async def create(
        self, 
        resource_type_id: Optional[int] = None,
        external_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        geometry: Optional[Union[Dict[str, Any], str]] = None,
        srid: Optional[int] = None,
        resource_type_name: Optional[str] = None
    ) -> Resource:
        """Create a new resource."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            
            if resource_type_id is None and resource_type_name:
                resource_type_id = await self._resolve_resource_type_id(realm_id_int, resource_type_name, session=session)
            
            if resource_type_id is None:
                raise ValueError("resource_type_id or resource_type_name required")
            
            service = ResourceService(session)
            
            resource_create = ResourceCreate(
                resource_type_id=resource_type_id,
                external_id=external_id,
                attributes=attributes,
                geometry=geometry,
                srid=srid
            )
            
            created = await service.create_resource(realm_id_int, resource_create)
            return self._map_resource(created)
    
    async def get(
        self, 
        resource_id: Union[int, str],
        resource_type: Optional[Union[int, str]] = None
    ) -> Resource:
        """Get a resource by ID or external ID.
        
        If resource_type is provided, treats resource_id as external_id and looks up by that.
        If resource_type is not provided and resource_id is numeric, treats it as internal ID.
        """
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceService(session)
            
            # If resource_type is provided, always use external_id lookup
            if resource_type is not None:
                type_id_or_name = str(resource_type)
                resource = await service.get_resource_by_external_id(realm_id_int, type_id_or_name, str(resource_id))
            elif isinstance(resource_id, int) or (isinstance(resource_id, str) and resource_id.isdigit()):
                # No resource_type, and resource_id looks like an internal ID
                resource = await service.get_resource(realm_id_int, int(resource_id))
            else:
                # Non-numeric resource_id without resource_type - can't determine lookup method
                raise ValueError("resource_type required when using non-numeric external_id")
            
            if resource is None:
                raise ValueError(f"Resource '{resource_id}' not found")
            
            return self._map_resource(resource)
    
    async def update(
        self, 
        resource_id: Union[int, str],
        resource_type: Optional[Union[int, str]] = None,
        resource_type_id: Optional[int] = None,
        external_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        geometry: Optional[Union[Dict[str, Any], str]] = None,
        srid: Optional[int] = None
    ) -> Resource:
        """Update a resource."""
        # Get the resource first to resolve ID (uses its own session)
        resource_dto = await self.get(resource_id, resource_type)
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceService(session)
            
            resource_update = ResourceUpdate(
                external_id=external_id,
                attributes=attributes,
                geometry=geometry,
                srid=srid
            )
            
            updated = await service.update_resource(realm_id_int, resource_dto.id, resource_update)
            
            if updated is None:
                raise ValueError(f"Resource '{resource_id}' not found")
            
            return self._map_resource(updated)
    
    async def delete(
        self, 
        resource_id: Union[int, str],
        resource_type: Optional[Union[int, str]] = None
    ) -> Dict[str, Any]:
        """Delete a resource."""
        # Get the resource first to resolve ID (uses its own session)
        resource_dto = await self.get(resource_id, resource_type)
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceService(session)
            success = await service.delete_resource(realm_id_int, resource_dto.id)
            
            if not success:
                raise ValueError(f"Resource '{resource_id}' not found")
            
            return {"status": "deleted"}
    
    async def list(self) -> List[Resource]:
        """List all resources in a realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceService(session)
            resources = await service.list_resources(realm_id_int)
            
            return [self._map_resource(r) for r in resources]
    
    async def sync(
        self, 
        resources: List[Resource]
    ) -> Dict[str, Any]:
        """Sync resources (create if not exist)."""
        return await self.batch_update(create=resources)
    
    async def set_public(
        self, 
        resource_id: int,
        resource_type_id: Optional[int] = None,
        action_id: Optional[int] = None,
        is_public: bool = True,
        resource_type_name: Optional[str] = None,
        action_name: Optional[str] = None
    ) -> bool:
        """
        Make a specific resource public (Level 3) or private.
        Supports resolution by Name OR ID.
        """
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
        
        # We need to resolve names to IDs if not provided, but DB managers usually require IDs or resolve internally
        # Logic adapted from HTTP ResourceManager
        
        # Access lookup service via client if needed, or resolve internally
        # Since we are in DB mode, we can use other managers directly but usually they need a session.
        # However, `client.lookup` might be None in DB mode (as verified in db.py).
        # We should use internal resolution helpers if possible or other managers.
        
        if resource_type_id is None and resource_type_name:
            # We can use _resolve_resource_type_id helper from DBBaseManager
            async with self._db_session.get_session() as session:
                 resource_type_id = await self._resolve_resource_type_id(realm_id_int, resource_type_name, session=session)
            
        if action_id is None and action_name:
             # We need a helper for action resolution. DBBaseManager might not have it yet?
             # Let's check DBActionManager.
             # Alternatively, we can use the client's action manager list/get?
             # For now, let's assume IDs are passed or we fetch via DBActionManager logic.
             # Ideally we should implement _resolve_action_id in DBBaseManager if missing.
             pass

        if resource_type_id is None: raise ValueError("resource_type_id or resource_type_name required")
        if action_id is None and action_name is None: raise ValueError("action_id or action_name required")
        
        # If action_id is still missing, we really need to resolve it.
        if action_id is None:
             # Fallback to fetching action by name manually if no helper
              async with self._db_session.get_session() as session:
                  from sqlalchemy import select
                  from common.models import Action
                  stmt = select(Action.id).where(Action.realm_id == realm_id_int, Action.name == action_name)
                  action_id = (await session.execute(stmt)).scalar_one_or_none()
        
        if action_id is None: raise ValueError(f"Action '{action_name}' not found")

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
    
    async def batch_update(
        self,
        create: Optional[List[Any]] = None,
        update: Optional[List[Any]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """Batch create/update/delete resources."""
        from common.schemas.realm_api import ResourceBatchUpdateItem, ResourceBatchDeleteItem
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceService(session)
            
            operation = BatchResourceOperation()
            
            if create:
                for item in create:
                    item_dict = item.model_dump(exclude_unset=True) if hasattr(item, 'model_dump') else item
                    
                    # Resolve resource type if name provided
                    type_id = item_dict.get("resource_type_id")
                    if type_id is None and item_dict.get("resource_type_name"):
                        type_id = await self._resolve_resource_type_id(
                            realm_id_int, item_dict.get("resource_type_name"), session=session
                        )
                    
                    operation.create.append(ResourceCreate(
                        resource_type_id=type_id,
                        external_id=item_dict.get("external_id"),
                        attributes=item_dict.get("attributes"),
                        geometry=item_dict.get("geometry"),
                        srid=item_dict.get("srid")
                    ))
            
            if update:
                for item in update:
                    item_dict = item.model_dump(exclude_unset=True) if hasattr(item, 'model_dump') else item
                    operation.update.append(ResourceBatchUpdateItem(
                        id=item_dict.get("id"),
                        external_id=item_dict.get("external_id"),
                        resource_type_id=item_dict.get("resource_type_id"),
                        attributes=item_dict.get("attributes"),
                        geometry=item_dict.get("geometry"),
                        srid=item_dict.get("srid")
                    ))
            
            if delete:
                for item in delete:
                    if isinstance(item, int):
                        operation.delete.append(item)
                    elif isinstance(item, dict):
                        operation.delete.append(ResourceBatchDeleteItem(
                            id=item.get("id"),
                            external_id=item.get("external_id"),
                            resource_type_id=item.get("resource_type_id")
                        ))
            
            await service.batch_resources(realm_id_int, operation)
            
            return {
                "created": len(operation.create),
                "updated": len(operation.update),
                "deleted": len(operation.delete)
            }
    
    def _map_resource(self, resource_read) -> Resource:
        """Map ResourceRead to SDK Resource model."""
        ext_id = None
        if hasattr(resource_read, 'external_id'):
            ext_id = resource_read.external_id
            if isinstance(ext_id, list) and ext_id:
                ext_id = ext_id[0]  # Take first external ID
        
        return Resource(
            id=resource_read.id,
            realm_id=resource_read.realm_id,
            resource_type_id=resource_read.resource_type_id,
            attributes=resource_read.attributes,
            external_id=ext_id
        )
