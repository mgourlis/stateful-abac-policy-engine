from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, insert
from sqlalchemy.orm import selectinload
from common.models import Principal, AuthRole, PrincipalRoles, ACL
from common.schemas.realm_api import PrincipalCreate, PrincipalUpdate, BatchPrincipalOperation
from common.services.cache import CacheService

class PrincipalService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_principal(self, realm_id: int, principal_in: PrincipalCreate) -> Principal:
        principal = Principal(username=principal_in.username, realm_id=realm_id, attributes=principal_in.attributes or {})
        self.session.add(principal)
        await self.session.commit()
        await self.session.refresh(principal)
        
        if principal_in.roles:
            stmt = select(AuthRole).where(AuthRole.realm_id == realm_id, AuthRole.name.in_(principal_in.roles))
            result = await self.session.execute(stmt)
            assigned_roles = result.scalars().all()
            
            if len(assigned_roles) != len(set(principal_in.roles)):
                found_names = {r.name for r in assigned_roles}
                missing = set(principal_in.roles) - found_names
                await self.session.delete(principal)
                await self.session.commit()
                raise ValueError(f"Roles not found: {missing}")
                
            mappings = [{"principal_id": principal.id, "role_id": r.id} for r in assigned_roles]
            if mappings:
                await self.session.execute(insert(PrincipalRoles).values(mappings))
                await self.session.commit()
                await CacheService.invalidate_principal_roles(principal.id)

        stmt_refresh = select(Principal).where(Principal.id == principal.id).options(selectinload(Principal.roles))
        return (await self.session.execute(stmt_refresh)).scalar_one()

    async def get_principal(self, realm_id: int, principal_id: int) -> Optional[Principal]:
        stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.id == principal_id, Principal.realm_id == realm_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_principals(self, realm_id: int) -> List[Principal]:
        stmt = select(Principal).where(Principal.realm_id == realm_id).options(selectinload(Principal.roles))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_principal(self, realm_id: int, principal_id: int, principal_update: PrincipalUpdate) -> Optional[Principal]:
        principal = await self.get_principal(realm_id, principal_id)
        if not principal:
            return None
            
        update_data = principal_update.model_dump(exclude_unset=True)
        if "username" in update_data:
            principal.username = update_data["username"]
        if "attributes" in update_data:
            principal.attributes = update_data["attributes"]
        
        await self.session.commit()
        
        if "roles" in update_data:
            role_names = update_data["roles"]
            if role_names is not None:
                stmt_roles = select(AuthRole).where(AuthRole.realm_id == realm_id, AuthRole.name.in_(role_names))
                result_roles = await self.session.execute(stmt_roles)
                new_roles = result_roles.scalars().all()
                if len(new_roles) != len(set(role_names)):
                    found_names = {r.name for r in new_roles}
                    missing = set(role_names) - found_names
                    raise ValueError(f"Roles not found: {missing}")
                
                await self.session.execute(delete(PrincipalRoles).where(PrincipalRoles.principal_id == principal_id))
                mappings = [{"principal_id": principal_id, "role_id": r.id} for r in new_roles]
                if mappings:
                    await self.session.execute(insert(PrincipalRoles).values(mappings))
                await self.session.commit()
                await CacheService.invalidate_principal_roles(principal_id)
        
        stmt_refresh = select(Principal).where(Principal.id == principal_id).options(selectinload(Principal.roles))
        return (await self.session.execute(stmt_refresh)).scalar_one()

    async def delete_principal(self, realm_id: int, principal_id: int) -> bool:
        principal = await self.get_principal(realm_id, principal_id)
        if not principal:
            return False
            
        await self.session.execute(delete(PrincipalRoles).where(PrincipalRoles.principal_id == principal_id))
        await self.session.execute(delete(ACL).where(ACL.principal_id == principal_id))
        await self.session.delete(principal)
        await self.session.commit()
        await CacheService.invalidate_principal_roles(principal_id)
        return True

    async def batch_principals(self, realm_id: int, operation: BatchPrincipalOperation) -> BatchPrincipalOperation:
        if operation.create:
            for p_data in operation.create:
                existing = await self.session.execute(select(Principal).options(selectinload(Principal.roles)).where(Principal.realm_id == realm_id, Principal.username == p_data.username))
                if existing.scalar_one_or_none():
                    continue
                p = Principal(**p_data.model_dump(), realm_id=realm_id)
                self.session.add(p)
        
        if operation.update:
             for p_data in operation.update:
                pid = p_data.id
                username = p_data.username
                stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.realm_id == realm_id)
                if pid:
                    stmt = stmt.where(Principal.id == pid)
                elif username:
                    stmt = stmt.where(Principal.username == username)
                else:
                    continue
                result = await self.session.execute(stmt)
                p = result.scalar_one_or_none()
                if p:
                    update_fields = p_data.model_dump(exclude_unset=True, exclude={"id", "username"})
                    for k, v in update_fields.items():
                        if hasattr(p, k):
                            setattr(p, k, v)
                    self.session.add(p)

        if operation.delete:
             stmt = delete(Principal).where(Principal.realm_id == realm_id, Principal.id.in_(operation.delete))
             await self.session.execute(stmt)

        await self.session.commit()
        return operation
