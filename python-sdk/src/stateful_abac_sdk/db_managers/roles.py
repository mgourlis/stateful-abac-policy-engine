"""
DB Manager for Role operations.
"""
from typing import List, Dict, Any, Optional, Union
from .base import DBBaseManager
from ..models import Role
from ..interfaces import IRoleManager
from common.application.role_service import RoleService
from common.schemas.realm_api import AuthRoleCreate, AuthRoleUpdate


class DBRoleManager(DBBaseManager, IRoleManager):
    """DB-mode manager for role operations."""
    
    async def create(
        self, 
        name: str,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Role:
        """Create a new role."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = RoleService(session)
            
            role_create = AuthRoleCreate(
                name=name,
                attributes=attributes
            )
            
            created = await service.create_role(realm_id_int, role_create)
            return self._map_role(created)
    
    async def list(self) -> List[Role]:
        """List all roles in a realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = RoleService(session)
            roles = await service.list_roles(realm_id_int)
            
            return [self._map_role(r) for r in roles]
    
    async def sync(self, roles: List[Role]) -> Dict[str, Any]:
        """Sync roles using batch endpoint."""
        return await self.batch_update(create=roles)
    
    async def batch_update(
        self,
        create: Optional[List[Role]] = None,
        update: Optional[List[Role]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """Batch create/update/delete roles."""
        from common.schemas.realm_api import BatchRoleOperation, RoleBatchUpdateItem
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = RoleService(session)
            
            operation = BatchRoleOperation()
            
            if create:
                for item in create:
                    operation.create.append(AuthRoleCreate(
                        name=item.name,
                        attributes=item.attributes
                    ))
            
            if update:
                for item in update:
                    operation.update.append(RoleBatchUpdateItem(
                        id=item.id,
                        name=item.name,
                        attributes=item.attributes
                    ))
            
            if delete:
                delete_ids = []
                for d in delete:
                    if isinstance(d, int):
                        delete_ids.append(d)
                    elif hasattr(d, 'id') and d.id:
                        delete_ids.append(d.id)
                operation.delete = delete_ids
            
            await service.batch_roles(realm_id_int, operation)
            
            return {
                "created": [c.name for c in operation.create],
                "updated": [u.id for u in operation.update if u.id],
                "deleted": operation.delete
            }
    
    async def get(self, role_id: Union[int, str]) -> Role:
        """Get a role."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            role_id_int = await self._resolve_role_id(realm_id_int, role_id, session=session)
            service = RoleService(session)
            role = await service.get_role(realm_id_int, role_id_int)
            
            if role is None:
                raise ValueError(f"Role {role_id} not found")
            
            return self._map_role(role)
    
    async def update(
        self, 
        role_id: Union[int, str],
        name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Role:
        """Update a role."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            role_id_int = await self._resolve_role_id(realm_id_int, role_id, session=session)
            service = RoleService(session)
            
            update_data = {}
            if name is not None: update_data["name"] = name
            if attributes is not None: update_data["attributes"] = attributes
            
            role_update = AuthRoleUpdate(**update_data)
            
            updated = await service.update_role(realm_id_int, role_id_int, role_update)
            
            if updated is None:
                raise ValueError(f"Role {role_id} not found")
            
            return self._map_role(updated)
    
    async def delete(self, role_id: Union[int, str], realm_id: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        """Delete a role."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(realm_id, session=session)
            role_id_int = await self._resolve_role_id(realm_id_int, role_id, session=session)
            service = RoleService(session)
            success = await service.delete_role(realm_id_int, role_id_int)
            
            if not success:
                raise ValueError(f"Role {role_id} not found")
            
            return {"status": "deleted"}
    
    def _map_role(self, role_orm) -> Role:
        """Map ORM AuthRole to SDK Role model."""
        return Role(
            id=role_orm.id,
            name=role_orm.name,
            realm_id=role_orm.realm_id,
            attributes=role_orm.attributes
        )
