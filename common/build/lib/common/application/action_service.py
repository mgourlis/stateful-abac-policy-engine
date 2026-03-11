from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from common.models import Action
from common.schemas.realm_api import ActionCreate, ActionUpdate, BatchActionOperation
from .realm_service import RealmService

class ActionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_action(self, realm_id: int, action_in: ActionCreate) -> Action:
        obj = Action(name=action_in.name, realm_id=realm_id)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        await self._invalidate_realm_cache(realm_id)
        return obj

    async def get_action(self, realm_id: int, action_id: int) -> Optional[Action]:
        stmt = select(Action).where(Action.id == action_id, Action.realm_id == realm_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_actions(self, realm_id: int, skip: int = 0, limit: int = 100) -> List[Action]:
        stmt = select(Action).where(Action.realm_id == realm_id).offset(skip).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def update_action(self, realm_id: int, action_id: int, action_in: ActionUpdate) -> Optional[Action]:
        obj = await self.get_action(realm_id, action_id)
        if not obj:
            return None
        
        if action_in.name:
            obj.name = action_in.name
            
        await self.session.commit()
        await self.session.refresh(obj)
        await self._invalidate_realm_cache(realm_id)
        return obj

    async def delete_action(self, realm_id: int, action_id: int) -> bool:
        obj = await self.get_action(realm_id, action_id)
        if not obj:
            return False
            
        await self.session.delete(obj)
        await self.session.commit()
        await self._invalidate_realm_cache(realm_id)
        return True

    async def batch_actions(self, realm_id: int, operation: BatchActionOperation) -> BatchActionOperation:
        if operation.create:
            for data in operation.create:
                existing = await self.session.execute(select(Action).where(Action.realm_id == realm_id, Action.name == data.name))
                if existing.scalar_one_or_none():
                    continue
                obj = Action(**data.model_dump(), realm_id=realm_id)
                self.session.add(obj)
                
        if operation.update:
            for data in operation.update:
                oid = data.id
                name = data.name
                stmt = select(Action).where(Action.realm_id == realm_id)
                if oid:
                     stmt = stmt.where(Action.id == oid)
                elif name:
                     stmt = stmt.where(Action.name == name)
                else:
                    continue
                res = await self.session.execute(stmt)
                obj = res.scalar_one_or_none()
                if obj:
                    if data.name: obj.name = data.name
                    self.session.add(obj)

        if operation.delete:
             stmt = delete(Action).where(Action.realm_id == realm_id, Action.id.in_(operation.delete))
             await self.session.execute(stmt)

        await self.session.commit()
        return operation

    async def _invalidate_realm_cache(self, realm_id: int):
         realm_service = RealmService(self.session)
         realm = await realm_service.get_realm(realm_id)
         if realm:
             from common.services.cache import CacheService
             await CacheService.invalidate_realm(realm.name)
