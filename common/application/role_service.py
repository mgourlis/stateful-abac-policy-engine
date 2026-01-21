from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from common.models import AuthRole, PrincipalRoles, ACL
from common.schemas.realm_api import AuthRoleCreate, AuthRoleUpdate, BatchRoleOperation
from common.services.cache import CacheService
from .realm_service import RealmService

class RoleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_role(self, realm_id: int, role_in: AuthRoleCreate) -> AuthRole:
        role = AuthRole(name=role_in.name, realm_id=realm_id, attributes=role_in.attributes)
        self.session.add(role)
        await self.session.commit()
        await self.session.refresh(role)
        
        # Invalidate realm cache? The controller did.
        # Need realm name for that.
        await self._invalidate_realm_cache(realm_id)
        
        return role

    async def get_role(self, realm_id: int, role_id: int) -> Optional[AuthRole]:
        stmt = select(AuthRole).where(AuthRole.id == role_id, AuthRole.realm_id == realm_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_roles(self, realm_id: int) -> List[AuthRole]:
        stmt = select(AuthRole).where(AuthRole.realm_id == realm_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_role(self, realm_id: int, role_id: int, role_update: AuthRoleUpdate) -> Optional[AuthRole]:
        role = await self.get_role(realm_id, role_id)
        if not role:
            return None
        
        update_data = role_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(role, key, value)
        
        await self.session.commit()
        await self.session.refresh(role)
        
        await self._invalidate_realm_cache(realm_id)
        return role

    async def delete_role(self, realm_id: int, role_id: int) -> bool:
        role = await self.get_role(realm_id, role_id)
        if not role:
            return False
        
        # Get affected principals
        affected_stmt = select(PrincipalRoles.principal_id).where(PrincipalRoles.role_id == role_id)
        affected_result = await self.session.execute(affected_stmt)
        affected_principal_ids = affected_result.scalars().all()
        
        await self.session.execute(delete(PrincipalRoles).where(PrincipalRoles.role_id == role_id))
        await self.session.execute(delete(ACL).where(ACL.role_id == role_id))
        
        await self.session.delete(role)
        await self.session.commit()
        
        await self._invalidate_realm_cache(realm_id)
        for pid in affected_principal_ids:
            await CacheService.invalidate_principal_roles(pid)
            
        return True

    async def batch_roles(self, realm_id: int, operation: BatchRoleOperation) -> BatchRoleOperation:
        if operation.create:
            for data in operation.create:
                existing = await self.session.execute(select(AuthRole).where(AuthRole.realm_id == realm_id, AuthRole.name == data.name))
                if existing.scalar_one_or_none():
                    continue
                obj = AuthRole(**data.model_dump(), realm_id=realm_id)
                self.session.add(obj)

        if operation.update:
            for data in operation.update:
                oid = data.id
                name = data.name
                stmt = select(AuthRole).where(AuthRole.realm_id == realm_id)
                if oid:
                    stmt = stmt.where(AuthRole.id == oid)
                elif name:
                    stmt = stmt.where(AuthRole.name == name)
                else:
                    continue
                result = await self.session.execute(stmt)
                obj = result.scalar_one_or_none()
                if obj:
                    update_fields = data.model_dump(exclude_unset=True, exclude={"id", "name"})
                    for k, v in update_fields.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    self.session.add(obj)

        if operation.delete:
            stmt = delete(AuthRole).where(AuthRole.realm_id == realm_id, AuthRole.id.in_(operation.delete))
            await self.session.execute(stmt)

        await self.session.commit()
        return operation

    async def _invalidate_realm_cache(self, realm_id: int):
         # Helper to get name and invalidate
         # Could optimize by passing name if known or relying on RealmService cache logic
         # Reusing RealmService logic if possible
         realm_service = RealmService(self.session)
         realm = await realm_service.get_realm(realm_id)
         if realm:
             await CacheService.invalidate_realm(realm.name)
