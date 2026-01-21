"""
DB Manager for PrincipalModel operations.
"""
from typing import List, Dict, Any, Optional, Union
from .base import DBBaseManager
from ..models import Principal, Role
from ..interfaces import IPrincipalManager
from common.application.principal_service import PrincipalService
from common.schemas.realm_api import PrincipalCreate, PrincipalUpdate


class DBPrincipalManager(DBBaseManager, IPrincipalManager):
    """DB-mode manager for principal operations."""
    
    async def create(
        self, 
        username: str,
        attributes: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None
    ) -> Principal:
        """Create a new principal."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = PrincipalService(session)
            
            principal_create = PrincipalCreate(
                username=username,
                attributes=attributes,
                roles=roles
            )
            
            created = await service.create_principal(realm_id_int, principal_create)
            return self._map_principal(created)
    
    async def list(self) -> List[Principal]:
        """List all principals in a realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = PrincipalService(session)
            principals = await service.list_principals(realm_id_int)
            
            return [self._map_principal(p) for p in principals]
    
    async def get(self, principal_id: Union[int, str]) -> Principal:
        """Get a principal."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            principal_id_int = await self._resolve_principal_id(realm_id_int, principal_id, session=session)
            service = PrincipalService(session)
            principal = await service.get_principal(realm_id_int, principal_id_int)
            
            if principal is None:
                raise ValueError(f"Principal {principal_id} not found")
            
            return self._map_principal(principal)
    
    async def update(
        self, 
        principal_id: Union[int, str],
        username: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None
    ) -> Principal:
        """Update a principal."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            principal_id_int = await self._resolve_principal_id(realm_id_int, principal_id, session=session)
            service = PrincipalService(session)
            
            update_data = {}
            if username is not None: update_data["username"] = username
            if attributes is not None: update_data["attributes"] = attributes
            if roles is not None: update_data["roles"] = roles
            
            principal_update = PrincipalUpdate(**update_data)
            
            updated = await service.update_principal(realm_id_int, principal_id_int, principal_update)
            
            if updated is None:
                raise ValueError(f"Principal {principal_id} not found")
            
            return self._map_principal(updated)
    
    async def delete(self, principal_id: Union[int, str]) -> Dict[str, Any]:
        """Delete a principal."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            principal_id_int = await self._resolve_principal_id(realm_id_int, principal_id, session=session)
            service = PrincipalService(session)
            success = await service.delete_principal(realm_id_int, principal_id_int)
            
            if not success:
                raise ValueError(f"Principal {principal_id} not found")
            
            return {"status": "deleted"}
    
    async def sync(self, principals: List[Principal]) -> Dict[str, Any]:
        """Sync principals."""
        return await self.batch_update(create=principals)
    
    async def batch_update(
        self,
        create: Optional[List[Principal]] = None,
        update: Optional[List[Principal]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """Batch create/update/delete principals."""
        from common.schemas.realm_api import BatchPrincipalOperation, PrincipalBatchUpdateItem
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = PrincipalService(session)
            
            operation = BatchPrincipalOperation()
            
            if create:
                for item in create:
                    # Handle roles conversion if item is a Principal object
                    roles_list = None
                    if hasattr(item, 'roles') and item.roles:
                        roles_list = [r.name if hasattr(r, 'name') else str(r) for r in item.roles]
                    
                    operation.create.append(PrincipalCreate(
                        username=item.username,
                        attributes=item.attributes,
                        roles=roles_list
                    ))
            
            if update:
                for item in update:
                    operation.update.append(PrincipalBatchUpdateItem(
                        id=item.id,
                        username=item.username,
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
            
            await service.batch_principals(realm_id_int, operation)
            
            return {
                "created": [c.username for c in operation.create],
                "updated": [u.id for u in operation.update if u.id],
                "deleted": operation.delete
            }
    
    def _map_principal(self, principal_orm) -> Principal:
        """Map ORM Principal to SDK Principal model."""
        roles = []
        if principal_orm.roles:
            roles = [
                Role(
                    id=r.id,
                    name=r.name,
                    realm_id=r.realm_id,
                    attributes=r.attributes
                )
                for r in principal_orm.roles
            ]
        
        return Principal(
            id=principal_orm.id,
            username=principal_orm.username,
            realm_id=principal_orm.realm_id,
            attributes=principal_orm.attributes,
            roles=roles
        )
