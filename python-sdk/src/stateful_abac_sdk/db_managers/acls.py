"""
DB Manager for ACLModel operations.
"""
from typing import List, Dict, Any, Optional, Union
from .base import DBBaseManager
from ..models import ACL, ACLCreateResponse, ACLDeleteResponse
from ..interfaces import IACLManager
from common.application.acl_service import ACLService
from common.schemas.realm_api import ACLCreate, ACLUpdate, BatchACLOperation


class DBACLManager(DBBaseManager, IACLManager):
    """DB-mode manager for ACLModel operations."""
    
    async def create(
        self, 
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
        role_name: Optional[str] = None
    ) -> ACLCreateResponse:
        """Create a new ACLModel entry."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            
            # Resolve IDs from names
            if resource_type_id is None and resource_type_name:
                resource_type_id = await self._resolve_resource_type_id(realm_id_int, resource_type_name, session=session)
            if action_id is None and action_name:
                action_id = await self._resolve_action_id(realm_id_int, action_name, session=session)
            if principal_id is None and principal_name:
                principal_id = await self._resolve_principal_id(realm_id_int, principal_name, session=session)
            if role_id is None and role_name:
                role_id = await self._resolve_role_id(realm_id_int, role_name, session=session)
            
            # Handle mutual exclusion for principal/role
            if role_id is not None and role_id != 0:
                principal_id = None
            else:
                principal_id = principal_id if principal_id is not None else 0
                role_id = None
            
            service = ACLService(session)
            
            acl_create = ACLCreate(
                realm_id=realm_id_int,
                resource_type_id=resource_type_id,
                action_id=action_id,
                principal_id=principal_id,
                role_id=role_id,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                conditions=conditions
            )
            
            created_data = await service.create_acl(realm_id_int, acl_create)
            return ACLCreateResponse(**created_data)
    
    async def get(self, acl_id: int) -> ACL:
        """Get an ACLModel by ID."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ACLService(session)
            acl_data = await service.get_acl(realm_id_int, acl_id)
            
            if acl_data is None:
                raise ValueError(f"ACL {acl_id} not found")
            
            return self._map_acl(acl_data)
    
    async def list(
        self, 
        resource_type_id: Optional[int] = None,
        action_id: Optional[int] = None,
        principal_id: Optional[int] = None,
        role_id: Optional[int] = None,
        resource_id: Optional[int] = None,
        # Name-based filtering
        resource_type_name: Optional[str] = None,
        action_name: Optional[str] = None,
        principal_name: Optional[str] = None,
        role_name: Optional[str] = None
    ) -> List[ACL]:
        """List ACLs with optional filtering."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            
            # Resolve names to IDs
            if resource_type_name and not resource_type_id:
                resource_type_id = await self._resolve_resource_type_id(realm_id_int, resource_type_name, session=session)
            if action_name and not action_id:
                action_id = await self._resolve_action_id(realm_id_int, action_name, session=session)
            if principal_name and principal_id is None:
                principal_id = await self._resolve_principal_id(realm_id_int, principal_name, session=session)
            if role_name and role_id is None:
                role_id = await self._resolve_role_id(realm_id_int, role_name, session=session)
            
            filters = {}
            if resource_type_id is not None:
                filters["resource_type_id"] = resource_type_id
            if action_id is not None:
                filters["action_id"] = action_id
            if principal_id is not None:
                filters["principal_id"] = principal_id
            if role_id is not None:
                filters["role_id"] = role_id
            if resource_id is not None:
                filters["resource_id"] = resource_id
            
            service = ACLService(session)
            acls_data = await service.list_all_acls(realm_id_int, filters=filters)
            
            return [self._map_acl(a) for a in acls_data]
    
    async def update(
        self, 
        acl_id: int,
        conditions: Optional[Dict[str, Any]] = None
    ) -> ACL:
        """Update an ACLModel."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ACLService(session)
            
            acl_update = ACLUpdate(conditions=conditions)
            updated_data = await service.update_acl(realm_id_int, acl_id, acl_update)
            
            if updated_data is None:
                raise ValueError(f"ACL {acl_id} not found")
            
            return self._map_acl(updated_data)
    
    async def delete(self, acl_id: int) -> Dict[str, Any]:
        """Delete an ACLModel."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ACLService(session)
            success = await service.delete_acl(realm_id_int, acl_id)
            
            if not success:
                raise ValueError(f"ACL {acl_id} not found")
            
            return {"deleted": True, "id": acl_id}
    
    async def sync(
        self, 
        acls: List[ACL]
    ) -> Dict[str, Any]:
        """Sync ACLs (ensure they exist)."""
        return await self.batch_update(create=acls)
    
    async def batch_update(
        self,
        create: Optional[List[Any]] = None,
        update: Optional[List[Any]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """Batch create/update/delete ACLs."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ACLService(session)
            
            operation = BatchACLOperation()
            
            if create:
                for item in create:
                    item_dict = item.model_dump(exclude_unset=True) if hasattr(item, 'model_dump') else item
                    
                    # Resolve names to IDs (same logic as create method)
                    resource_type_id = item_dict.get("resource_type_id")
                    action_id = item_dict.get("action_id")
                    principal_id = item_dict.get("principal_id")
                    role_id = item_dict.get("role_id")
                    
                    if resource_type_id is None and item_dict.get("resource_type_name"):
                        resource_type_id = await self._resolve_resource_type_id(realm_id_int, item_dict["resource_type_name"], session=session)
                    if action_id is None and item_dict.get("action_name"):
                        action_id = await self._resolve_action_id(realm_id_int, item_dict["action_name"], session=session)
                    if principal_id is None and item_dict.get("principal_name"):
                        principal_id = await self._resolve_principal_id(realm_id_int, item_dict["principal_name"], session=session)
                    if role_id is None and item_dict.get("role_name"):
                        role_id = await self._resolve_role_id(realm_id_int, item_dict["role_name"], session=session)
                    
                    # Handle mutual exclusion for principal/role
                    if role_id is not None and role_id != 0:
                        principal_id = None
                    else:
                        principal_id = principal_id if principal_id is not None else 0
                        role_id = None
                    
                    operation.create.append(ACLCreate(
                        realm_id=realm_id_int,
                        resource_type_id=resource_type_id,
                        action_id=action_id,
                        principal_id=principal_id,
                        role_id=role_id,
                        resource_id=item_dict.get("resource_id"),
                        resource_external_id=item_dict.get("resource_external_id"),
                        conditions=item_dict.get("conditions")
                    ))
            
            if update:
                for item in update:
                    item_dict = item.model_dump(exclude_unset=True) if hasattr(item, 'model_dump') else item
                    operation.update.append(ACLUpdate(
                        resource_type_id=item_dict.get("resource_type_id"),
                        action_id=item_dict.get("action_id"),
                        principal_id=item_dict.get("principal_id"),
                        role_id=item_dict.get("role_id"),
                        resource_id=item_dict.get("resource_id"),
                        resource_external_id=item_dict.get("resource_external_id"),
                        conditions=item_dict.get("conditions")
                    ))
            
            if delete:
                for acl_id in delete:
                    if isinstance(acl_id, int):
                        # Service's batch_acls uses selector-based delete, not ID
                        # For IDs, delete one by one
                        await service.delete_acl(realm_id_int, acl_id)
            
            if operation.create or operation.update:
                await service.batch_acls(realm_id_int, operation)
            
            return {
                "created": len(operation.create),
                "updated": len(operation.update),
                "deleted": len(delete) if delete else 0
            }
    
    async def delete_by_key(
        self,
        resource_type_id: Optional[int] = None,
        action_id: Optional[int] = None,
        principal_id: Optional[int] = None,
        role_id: Optional[int] = None,
        resource_id: Optional[int] = None,
        resource_external_id: Optional[str] = None,
        # Name-based alternatives
        resource_type_name: Optional[str] = None,
        action_name: Optional[str] = None,
        principal_name: Optional[str] = None,
        role_name: Optional[str] = None,
    ) -> ACLDeleteResponse:
        """Delete ACL by compound key (not by ID)."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            
            # Resolve IDs from names
            if resource_type_id is None and resource_type_name:
                resource_type_id = await self._resolve_resource_type_id(realm_id_int, resource_type_name, session=session)
            if action_id is None and action_name:
                action_id = await self._resolve_action_id(realm_id_int, action_name, session=session)
            if principal_id is None and principal_name:
                principal_id = await self._resolve_principal_id(realm_id_int, principal_name, session=session)
            if role_id is None and role_name:
                role_id = await self._resolve_role_id(realm_id_int, role_name, session=session)
            
            # Handle mutual exclusion for principal/role
            if role_id is not None and role_id != 0:
                principal_id = None
            else:
                principal_id = principal_id if principal_id is not None else 0
                role_id = None
            
            service = ACLService(session)
            deleted_data = await service.delete_acl_by_key(
                realm_id=realm_id_int,
                resource_type_id=resource_type_id,
                action_id=action_id,
                principal_id=principal_id,
                role_id=role_id,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
            )
            
            return ACLDeleteResponse(
                deleted=deleted_data is not None, 
                acl=self._map_acl(deleted_data) if deleted_data else None
            )
    
    def _map_acl(self, acl_data: Union[Dict[str, Any], Any]) -> ACL:
        """Map service dictionary or ORM ACL to SDK ACL model."""
        if isinstance(acl_data, dict):
            return ACL(**acl_data)
            
        # Fallback for ORM objects if any remain
        return ACL(
            id=acl_data.id,
            realm_id=acl_data.realm_id,
            resource_type_id=acl_data.resource_type_id,
            action_id=acl_data.action_id,
            principal_id=acl_data.principal_id,
            role_id=acl_data.role_id,
            resource_id=acl_data.resource_id,
            conditions=acl_data.conditions,
            compiled_sql=getattr(acl_data, 'compiled_sql', None)
        )
