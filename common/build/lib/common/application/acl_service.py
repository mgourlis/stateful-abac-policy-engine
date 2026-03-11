from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import joinedload
from common.models import ACL, ExternalID, ResourceType, Action, Principal, AuthRole, Resource
from common.schemas.realm_api import ACLCreate, ACLUpdate, BatchACLOperation, ACLRead

class ACLService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_acl(self, realm_id: int, acl_in: ACLCreate) -> Dict[str, Any]:
        """Create or update an ACL. Returns result dict with 'acl' and 'previous_state'."""
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
        
        previous_state = None
        if existing:
            # Capture names manual for previous_state
            prev_names = await self._get_acl_names(existing)
            previous_state = {
                "conditions": existing.conditions,
                **prev_names
            }
            
            if acl_in.conditions is not None:
                existing.conditions = acl_in.conditions
                self.session.add(existing)
                await self.session.commit()
                await self.session.refresh(existing)
            
            return {
                **await self._map_acl_to_dict(existing),
                "previous_state": previous_state,
                "status": "updated"
            }
        
        obj = ACL(**acl_in.model_dump(exclude={'resource_external_id'}))
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        
        return {
            **await self._map_acl_to_dict(obj),
            "previous_state": None,
            "status": "created"
        }

    async def _get_acl_names(self, acl: ACL) -> Dict[str, Any]:
        """Manually fetch names for an ACL object."""
        res = {
            "resource_type_name": None,
            "action_name": None,
            "principal_name": None,
            "role_name": None,
            "resource_external_id": None
        }
        
        if acl.resource_type_id:
            rt = await self.session.get(ResourceType, acl.resource_type_id)
            if rt: res["resource_type_name"] = rt.name
            
        if acl.action_id:
            act = await self.session.get(Action, acl.action_id)
            if act: res["action_name"] = act.name
            
        if acl.principal_id:
            p = await self.session.get(Principal, acl.principal_id)
            if p: res["principal_name"] = p.username
            
        if acl.role_id:
            r = await self.session.get(AuthRole, acl.role_id)
            if r: res["role_name"] = r.name
            
        if acl.resource_id:
            # Get external ID
             stmt = select(ExternalID.external_id).where(
                 ExternalID.realm_id == acl.realm_id,
                 ExternalID.resource_id == acl.resource_id,
                 ExternalID.resource_type_id == acl.resource_type_id
             )
             res["resource_external_id"] = (await self.session.execute(stmt)).scalar()
             
        return res

    async def _map_acl_to_dict(self, acl: ACL) -> Dict[str, Any]:
        """Convert ACL model to dictionary with resolved names."""
        names = await self._get_acl_names(acl)
        return {
            "id": acl.id,
            "realm_id": acl.realm_id,
            "resource_type_id": acl.resource_type_id,
            "action_id": acl.action_id,
            "principal_id": acl.principal_id,
            "role_id": acl.role_id,
            "resource_id": acl.resource_id,
            "conditions": acl.conditions,
            **names
        }

    async def get_acl(self, realm_id: int, acl_id: int) -> Optional[Dict[str, Any]]:
        stmt = select(ACL).where(ACL.id == acl_id, ACL.realm_id == realm_id)
        obj = (await self.session.execute(stmt)).scalar_one_or_none()
        if not obj:
            return None
        return await self._map_acl_to_dict(obj)

    async def list_acls(self, realm_id: int, skip: int = 0, limit: int = 100, filters: dict = {}) -> Tuple[List[Dict[str, Any]], int]:
        stmt = select(ACL).where(ACL.realm_id == realm_id)
        for k, v in filters.items():
            if v is not None and hasattr(ACL, k):
                if k == 'resource_id':
                     stmt = stmt.where(ACL.resource_id == v)
                else:
                    stmt = stmt.where(getattr(ACL, k) == v)
        
        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0
        
        # Paginate
        stmt = stmt.offset(skip).limit(limit)
        items = (await self.session.execute(stmt)).scalars().all()
        
        # Map with names
        mapped_items = []
        for item in items:
            mapped_items.append(await self._map_acl_to_dict(item))
            
        return mapped_items, total

    async def list_all_acls(self, realm_id: int, filters: dict = {}) -> List[Dict[str, Any]]:
        stmt = select(ACL).where(ACL.realm_id == realm_id)
        for k, v in filters.items():
            if v is not None and hasattr(ACL, k):
                if k == 'resource_id':
                     stmt = stmt.where(ACL.resource_id == v)
                else:
                    stmt = stmt.where(getattr(ACL, k) == v)
        items = (await self.session.execute(stmt)).scalars().all()
        
        mapped_items = []
        for item in items:
            mapped_items.append(await self._map_acl_to_dict(item))
        return mapped_items

    async def update_acl(self, realm_id: int, acl_id: int, acl_in: ACLUpdate) -> Optional[Dict[str, Any]]:
        # Need the raw object for update
        stmt = select(ACL).where(ACL.id == acl_id, ACL.realm_id == realm_id)
        obj = (await self.session.execute(stmt)).scalar_one_or_none()
        
        if not obj:
            return None
        if acl_in.conditions is not None:
            obj.conditions = acl_in.conditions
        await self.session.commit()
        await self.session.refresh(obj)
        return await self._map_acl_to_dict(obj)

    async def delete_acl(self, realm_id: int, acl_id: int) -> bool:
        stmt = select(ACL).where(ACL.id == acl_id, ACL.realm_id == realm_id)
        obj = (await self.session.execute(stmt)).scalar_one_or_none()
        if not obj:
            return False
        await self.session.delete(obj)
        await self.session.commit()
        return True

    async def batch_acls(self, realm_id: int, operation: BatchACLOperation) -> BatchACLOperation:
        # Note: Batch operations don't currently return names in the operation object itself for performance
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

    async def _resolve_external(self, realm_id: int, rt_id: int, ext_id: str) -> Optional[ExternalID]:
        stmt = select(ExternalID).where(
            ExternalID.realm_id == realm_id,
            ExternalID.resource_type_id == rt_id,
            ExternalID.external_id == ext_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def delete_acl_by_key(
        self,
        realm_id: int,
        resource_type_id: int,
        action_id: int,
        principal_id: Optional[int],
        role_id: Optional[int],
        resource_id: Optional[int] = None,
        resource_external_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Delete ACL by unique compound key.
        
        Returns:
            The deleted ACL's data if found and deleted, None otherwise.
        """
        # Resolve external_id to resource_id if provided
        if resource_external_id and resource_type_id:
            ext_obj = await self._resolve_external(realm_id, resource_type_id, resource_external_id)
            if ext_obj:
                resource_id = ext_obj.resource_id
        
        # Fetch before deleting to return state for undo
        select_stmt = select(ACL).where(
            ACL.realm_id == realm_id,
            ACL.resource_type_id == resource_type_id,
            ACL.action_id == action_id,
            ACL.principal_id == principal_id,
            ACL.role_id == role_id,
            ACL.resource_id == resource_id,
        )
        acl_obj = (await self.session.execute(select_stmt)).scalar_one_or_none()
        
        if not acl_obj:
            return None
            
        acl_data = await self._map_acl_to_dict(acl_obj)
        
        await self.session.delete(acl_obj)
        await self.session.commit()
        return acl_data
