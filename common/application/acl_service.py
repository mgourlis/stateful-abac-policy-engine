from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from common.models import ACL, ExternalID
from common.schemas.realm_api import ACLCreate, ACLUpdate, BatchACLOperation, ACLRead

class ACLService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_acl(self, realm_id: int, acl_in: ACLCreate) -> ACL:
        # Resolve External
        if acl_in.resource_external_id:
            ext_obj = await self._resolve_external(realm_id, acl_in.resource_type_id, acl_in.resource_external_id)
            if not ext_obj:
                raise ValueError(f"External resource '{acl_in.resource_external_id}' not found")
            acl_in.resource_id = ext_obj.resource_id

        # Upsert Check
        stmt = select(ACL).where(
            ACL.realm_id == realm_id,
            ACL.resource_type_id == acl_in.resource_type_id,
            ACL.action_id == acl_in.action_id,
            ACL.principal_id == acl_in.principal_id,
            ACL.role_id == acl_in.role_id,
            ACL.resource_id == acl_in.resource_id
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        
        if existing:
            if acl_in.conditions is not None:
                existing.conditions = acl_in.conditions
                self.session.add(existing)
                await self.session.commit()
                await self.session.refresh(existing)
            return existing
        
        obj = ACL(**acl_in.model_dump(exclude={'resource_external_id'}))
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def get_acl(self, realm_id: int, acl_id: int) -> Optional[ACL]:
        stmt = select(ACL).where(ACL.id == acl_id, ACL.realm_id == realm_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_acls(self, realm_id: int, skip: int = 0, limit: int = 100, filters: dict = {}) -> tuple[List[ACL], int]:
        stmt = select(ACL).where(ACL.realm_id == realm_id)
        for k, v in filters.items():
            if v is not None and hasattr(ACL, k):
                if k == 'resource_id':
                     stmt = stmt.where(ACL.resource_id == v)
                else:
                    stmt = stmt.where(getattr(ACL, k) == v)
        
        # Count total
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0
        
        # Paginate
        stmt = stmt.offset(skip).limit(limit)
        items = (await self.session.execute(stmt)).scalars().all()
        
        return items, total

    async def list_all_acls(self, realm_id: int, filters: dict = {}) -> List[ACL]:
        stmt = select(ACL).where(ACL.realm_id == realm_id)
        for k, v in filters.items():
            if v is not None and hasattr(ACL, k):
                if k == 'resource_id':
                     stmt = stmt.where(ACL.resource_id == v)
                else:
                    stmt = stmt.where(getattr(ACL, k) == v)
        return (await self.session.execute(stmt)).scalars().all()

    async def update_acl(self, realm_id: int, acl_id: int, acl_in: ACLUpdate) -> Optional[ACL]:
        obj = await self.get_acl(realm_id, acl_id)
        if not obj:
            return None
        if acl_in.conditions is not None:
            obj.conditions = acl_in.conditions
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete_acl(self, realm_id: int, acl_id: int) -> bool:
        obj = await self.get_acl(realm_id, acl_id)
        if not obj:
            return False
        await self.session.delete(obj)
        await self.session.commit()
        return True

    async def batch_acls(self, realm_id: int, operation: BatchACLOperation) -> BatchACLOperation:
        if operation.create:
             for data in operation.create:
                 if data.resource_external_id:
                     ext_obj = await self._resolve_external(realm_id, data.resource_type_id, data.resource_external_id)
                     if ext_obj: data.resource_id = ext_obj.resource_id
                     else: continue # Skip if not found in batch?
                 
                 # Upsert
                 stmt = select(ACL).where(
                     ACL.realm_id == realm_id,
                     ACL.resource_type_id == data.resource_type_id,
                     ACL.action_id == data.action_id,
                     ACL.principal_id == data.principal_id,
                     ACL.role_id == data.role_id,
                     ACL.resource_id == data.resource_id
                 )
                 existing = (await self.session.execute(stmt)).scalar_one_or_none()
                 if existing:
                     if data.conditions is not None:
                         existing.conditions = data.conditions
                         self.session.add(existing)
                 else:
                     obj = ACL(**data.model_dump(exclude={'resource_external_id'}))
                     self.session.add(obj)

        if operation.update:
             for data in operation.update:
                 if data.resource_external_id:
                     ext_obj = await self._resolve_external(realm_id, data.resource_type_id, data.resource_external_id)
                     if ext_obj: data.resource_id = ext_obj.resource_id
                 
                 stmt = select(ACL).where(
                     ACL.realm_id == realm_id,
                     ACL.resource_type_id == data.resource_type_id,
                     ACL.action_id == data.action_id,
                     ACL.principal_id == data.principal_id,
                     ACL.role_id == data.role_id,
                     ACL.resource_id == data.resource_id
                 )
                 existing = (await self.session.execute(stmt)).scalar_one_or_none()
                 if existing:
                     if data.conditions is not None:
                         existing.conditions = data.conditions
                         self.session.add(existing)
        
        if operation.delete:
             for data in operation.delete:
                 if data.resource_external_id:
                     ext_obj = await self._resolve_external(realm_id, data.resource_type_id, data.resource_external_id)
                     if ext_obj: data.resource_id = ext_obj.resource_id
                 
                 stmt = delete(ACL).where(
                     ACL.realm_id == realm_id,
                     ACL.resource_type_id == data.resource_type_id,
                     ACL.action_id == data.action_id,
                     ACL.principal_id == data.principal_id,
                     ACL.role_id == data.role_id,
                     ACL.resource_id == data.resource_id
                 )
                 await self.session.execute(stmt)

        await self.session.commit()
        return operation

    async def _resolve_external(self, realm_id: int, type_id: int, ext_id: str) -> Optional[ExternalID]:
        stmt = select(ExternalID).where(
            ExternalID.realm_id == realm_id,
            ExternalID.resource_type_id == type_id,
            ExternalID.external_id == ext_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
