"""
DB Manager for ActionModel operations.
"""
from typing import List, Dict, Any, Optional, Union
from .base import DBBaseManager
from ..models import Action
from ..interfaces import IActionManager
from common.application.action_service import ActionService
from common.schemas.realm_api import ActionCreate, ActionUpdate


class DBActionManager(DBBaseManager, IActionManager):
    """DB-mode manager for action operations."""
    
    async def create(
        self, 
        name: str
    ) -> Action:
        """Create a new action."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ActionService(session)
            
            action_create = ActionCreate(name=name)
            created = await service.create_action(realm_id_int, action_create)
            
            return self._map_action(created)
    
    async def list(self) -> List[Action]:
        """List all actions in a realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ActionService(session)
            actions = await service.list_actions(realm_id_int, limit=10000)
            
            return [self._map_action(a) for a in actions]
    
    async def sync(self, actions: List[Action]) -> Dict[str, Any]:
        """Sync actions (ensure they exist)."""
        return await self.batch_update(create=actions)
    
    async def batch_update(
        self,
        create: Optional[List[Action]] = None,
        update: Optional[List[Action]] = None,
        delete: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """Batch create/update/delete actions."""
        from common.schemas.realm_api import BatchActionOperation, ActionBatchUpdateItem
        
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = ActionService(session)
            
            operation = BatchActionOperation()
            
            if create:
                for item in create:
                    operation.create.append(ActionCreate(name=item.name))
            
            if update:
                for item in update:
                    operation.update.append(ActionBatchUpdateItem(
                        id=item.id,
                        name=item.name
                    ))
            
            if delete:
                delete_ids = []
                for d in delete:
                    if isinstance(d, int):
                        delete_ids.append(d)
                    elif hasattr(d, 'id') and d.id:
                        delete_ids.append(d.id)
                operation.delete = delete_ids
            
            await service.batch_actions(realm_id_int, operation)
            
            return {
                "created": [c.name for c in operation.create],
                "updated": [u.id for u in operation.update if u.id],
                "deleted": operation.delete
            }
    
    async def get(self, action_id: Union[int, str]) -> Action:
        """Get an action."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            action_id_int = await self._resolve_action_id(realm_id_int, action_id, session=session)
            service = ActionService(session)
            action = await service.get_action(realm_id_int, action_id_int)
            
            if action is None:
                raise ValueError(f"Action {action_id} not found")
            
            return self._map_action(action)
    
    async def update(
        self, 
        action_id: Union[int, str],
        name: str
    ) -> Action:
        """Update an action."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            action_id_int = await self._resolve_action_id(realm_id_int, action_id, session=session)
            service = ActionService(session)
            
            action_update = ActionUpdate(name=name)
            updated = await service.update_action(realm_id_int, action_id_int, action_update)
            
            if updated is None:
                raise ValueError(f"Action {action_id} not found")
            
            return self._map_action(updated)
    
    async def delete(self, action_id: Union[int, str]) -> Dict[str, Any]:
        """Delete an action."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            action_id_int = await self._resolve_action_id(realm_id_int, action_id, session=session)
            service = ActionService(session)
            success = await service.delete_action(realm_id_int, action_id_int)
            
            if not success:
                raise ValueError(f"Action {action_id} not found")
            
            return {"status": "deleted"}
    
    def _map_action(self, action_orm) -> Action:
        """Map ORM Action to SDK Action model."""
        return Action(
            id=action_orm.id,
            name=action_orm.name,
            realm_id=action_orm.realm_id
        )
