"""
DB Manager for Resource Type operations.
"""
from typing import List, Dict, Any, Optional, Union
from .base import DBBaseManager
from ..models import ResourceType
from ..interfaces import IResourceTypeManager
from common.application.resource_type_service import ResourceTypeService
from common.schemas.realm_api import ResourceTypeCreate, ResourceTypeUpdate


class DBResourceTypeManager(DBBaseManager, IResourceTypeManager):
    """DB-mode manager for resource type operations."""
    
    async def create(
        self, 
        name: str,
        is_public: bool = False
    ) -> ResourceType:
        """Create a new resource type."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceTypeService(session)
            
            rt_create = ResourceTypeCreate(
                name=name,
                is_public=is_public
            )
            
            created_rt = await service.create_resource_type(realm_id_int, rt_create)
            
            return ResourceType(
                id=created_rt.id,
                name=created_rt.name,
                realm_id=created_rt.realm_id,
                is_public=created_rt.is_public
            )
    
    async def list(self) -> List[ResourceType]:
        """List all resource types in a realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceTypeService(session)
            resource_types = await service.list_resource_types(realm_id_int, limit=10000)
            
            return [
                ResourceType(
                    id=rt.id,
                    name=rt.name,
                    realm_id=rt.realm_id,
                    is_public=rt.is_public
                )
                for rt in resource_types
            ]
    
    async def sync(self, resource_types: List[ResourceType] = []) -> Dict[str, Any]:
        """Sync resource types (ensure they exist)."""
        return await self.batch_update(create=resource_types)
    
    async def batch_update(
        self,
        create: Optional[List[ResourceType]] = None,
        update: Optional[List[ResourceType]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """Batch create/update/delete resource types."""
        from common.schemas.realm_api import BatchResourceTypeOperation, ResourceTypeBatchUpdateItem
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ResourceTypeService(session)
            
            operation = BatchResourceTypeOperation()
            
            if create:
                for item in create:
                    operation.create.append(ResourceTypeCreate(
                        name=item.name,
                        is_public=item.is_public
                    ))
            
            if update:
                for item in update:
                    operation.update.append(ResourceTypeBatchUpdateItem(
                        id=item.id,
                        name=item.name,
                        is_public=item.is_public
                    ))
            
            if delete:
                delete_ids = []
                for d in delete:
                    if isinstance(d, int):
                        delete_ids.append(d)
                    elif hasattr(d, 'id') and d.id:
                        delete_ids.append(d.id)
                operation.delete = delete_ids
            
            await service.batch_resource_types(realm_id_int, operation)
            
            return {
                "created": [c.name for c in operation.create],
                "updated": [u.id for u in operation.update if u.id],
                "deleted": operation.delete
            }
    
    async def update(
        self, 
        type_id: Union[int, str],
        name: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> ResourceType:
        """Update a resource type."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            type_id_int = await self._resolve_resource_type_id(realm_id_int, type_id, session=session)
            service = ResourceTypeService(session)
            
            rt_update = ResourceTypeUpdate(
                name=name,
                is_public=is_public
            )
            
            updated_rt = await service.update_resource_type(realm_id_int, type_id_int, rt_update)
            
            if updated_rt is None:
                raise ValueError(f"ResourceType {type_id} not found")
            
            return ResourceType(
                id=updated_rt.id,
                name=updated_rt.name,
                realm_id=updated_rt.realm_id,
                is_public=updated_rt.is_public
            )
    
    async def set_public(
        self, 
        type_id: Union[int, str], 
        is_public: bool = True
    ) -> ResourceType:
        """Set the public status of a resource type."""
        return await self.update(type_id, is_public=is_public)
    
    async def get(self, type_id: Union[int, str]) -> ResourceType:
        """Get a resource type."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            type_id_int = await self._resolve_resource_type_id(realm_id_int, type_id, session=session)
            service = ResourceTypeService(session)
            resource_type = await service.get_resource_type(realm_id_int, type_id_int)
            
            if resource_type is None:
                raise ValueError(f"ResourceType {type_id} not found")
            
            return ResourceType(
                id=resource_type.id,
                name=resource_type.name,
                realm_id=resource_type.realm_id,
                is_public=resource_type.is_public
            )
    
    async def delete(self, type_id: Union[int, str]) -> Dict[str, Any]:
        """Delete a resource type."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            type_id_int = await self._resolve_resource_type_id(realm_id_int, type_id, session=session)
            service = ResourceTypeService(session)
            success = await service.delete_resource_type(realm_id_int, type_id_int)
            
            if not success:
                raise ValueError(f"ResourceType {type_id} not found")
            
            return {"status": "deleted"}
