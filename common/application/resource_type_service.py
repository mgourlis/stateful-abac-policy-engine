from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from common.models import ResourceType
from common.schemas.realm_api import ResourceTypeCreate, ResourceTypeUpdate, BatchResourceTypeOperation
from .realm_service import RealmService

class ResourceTypeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_resource_type(self, realm_id: int, rt_in: ResourceTypeCreate) -> ResourceType:
        obj = ResourceType(**rt_in.model_dump(), realm_id=realm_id)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        
        # Partitions
        try:
            rid = realm_id
            tid = obj.id
            await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS resource_{rid}_{tid} PARTITION OF resource_{rid} FOR VALUES IN ({tid})"))
            await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS acl_{rid}_{tid} PARTITION OF acl_{rid} FOR VALUES IN ({tid})"))
            await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS external_ids_{rid}_{tid} PARTITION OF external_ids_{rid} FOR VALUES IN ({tid})"))
            await self.session.commit()
        except Exception:
             # Log warning ideally
             pass

        await self._invalidate_realm_cache(realm_id)
        return obj

    async def get_resource_type(self, realm_id: int, rt_id: int) -> Optional[ResourceType]:
        stmt = select(ResourceType).where(ResourceType.id == rt_id, ResourceType.realm_id == realm_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_resource_types(self, realm_id: int, skip: int = 0, limit: int = 100) -> List[ResourceType]:
        stmt = select(ResourceType).where(ResourceType.realm_id == realm_id).offset(skip).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def update_resource_type(self, realm_id: int, rt_id: int, rt_in: ResourceTypeUpdate) -> Optional[ResourceType]:
        obj = await self.get_resource_type(realm_id, rt_id)
        if not obj:
            return None
        
        if rt_in.name is not None:
            obj.name = rt_in.name
        if rt_in.is_public is not None:
            obj.is_public = rt_in.is_public
            
        await self.session.commit()
        await self.session.refresh(obj)
        await self._invalidate_realm_cache(realm_id)
        return obj

    async def delete_resource_type(self, realm_id: int, rt_id: int) -> bool:
        obj = await self.get_resource_type(realm_id, rt_id)
        if not obj:
            return False
        
        # Drop Partitions
        try:
            rid = realm_id
            tid = rt_id
            await self.session.execute(text(f"DROP TABLE IF EXISTS resource_{rid}_{tid} CASCADE"))
            await self.session.execute(text(f"DROP TABLE IF EXISTS acl_{rid}_{tid} CASCADE"))
            await self.session.execute(text(f"DROP TABLE IF EXISTS external_ids_{rid}_{tid} CASCADE"))
        except Exception:
            pass

        await self.session.delete(obj)
        await self.session.commit()
        await self._invalidate_realm_cache(realm_id)
        return True

    async def batch_resource_types(self, realm_id: int, operation: BatchResourceTypeOperation) -> BatchResourceTypeOperation:
        if operation.create:
             for data in operation.create:
                existing = await self.session.execute(select(ResourceType).where(ResourceType.realm_id == realm_id, ResourceType.name == data.name))
                if existing.scalar_one_or_none():
                    continue
                obj = ResourceType(**data.model_dump(), realm_id=realm_id)
                self.session.add(obj)
                await self.session.flush()
                # Partitions
                try:
                    rid = realm_id
                    tid = obj.id
                    await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS resource_{rid}_{tid} PARTITION OF resource_{rid} FOR VALUES IN ({tid})"))
                    await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS acl_{rid}_{tid} PARTITION OF acl_{rid} FOR VALUES IN ({tid})"))
                    await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS external_ids_{rid}_{tid} PARTITION OF external_ids_{rid} FOR VALUES IN ({tid})"))
                except Exception:
                    pass

        if operation.update:
             for data in operation.update:
                 oid = data.id
                 name = data.name
                 stmt = select(ResourceType).where(ResourceType.realm_id == realm_id)
                 if oid: stmt = stmt.where(ResourceType.id == oid)
                 elif name: stmt = stmt.where(ResourceType.name == name)
                 else: continue
                 
                 res = await self.session.execute(stmt)
                 obj = res.scalar_one_or_none()
                 if obj:
                      if data.name is not None: obj.name = data.name
                      if data.is_public is not None: obj.is_public = data.is_public
                      self.session.add(obj)

        if operation.delete:
             stmt = delete(ResourceType).where(ResourceType.realm_id == realm_id, ResourceType.id.in_(operation.delete))
             await self.session.execute(stmt)

        await self.session.commit()
        return operation

    async def _invalidate_realm_cache(self, realm_id: int):
         realm_service = RealmService(self.session)
         realm = await realm_service.get_realm(realm_id)
         if realm:
             from common.services.cache import CacheService
             await CacheService.invalidate_realm(realm.name)
