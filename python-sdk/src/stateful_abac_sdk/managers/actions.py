from typing import List, Dict, Any, Optional, Union
from ..models import Action
from .base import BaseManager
from ..interfaces import IActionManager

class ActionManager(BaseManager, IActionManager):
    async def create(self, name: str) -> Action:
        """
        Create an action.

        Args:
            name: Name of the action.

        Returns:
            The created Action object.
        """
        realm_id = await self._resolve_realm_id()
        response = await self._post(f"/realms/{realm_id}/actions", json={"name": name})
        self.client.lookup.invalidate(realm_id, "actions")
        return Action(**response)

    async def list(self) -> List[Action]:
        """
        List actions in a realm.

        Returns:
            List of Action objects.
        """
        realm_id = await self._resolve_realm_id()
        response = await self._get(f"/realms/{realm_id}/actions")
        return [Action(**item) for item in response]

    async def sync(self, actions: List[Action]) -> Dict[str, Any]:
        """
        Sync actions (ensure they exist).

        Args:
            actions: List of Action objects.

        Returns:
            Batch response.
        """
        return await self.batch_update(create=actions)

    async def batch_update(self, create: Optional[List[Action]] = None,
                           update: Optional[List[Action]] = None,
                           delete: Optional[List[Any]] = None) -> Dict[str, Any]:
        realm_id = await self._resolve_realm_id()
        payload = {}
        if create: 
            payload["create"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in create]
        if update: 
            payload["update"] = [r.model_dump(exclude_unset=True) if hasattr(r, 'model_dump') else r for r in update]
        if delete: 
            payload["delete"] = delete
        return await self._post(f"/realms/{realm_id}/actions/batch", json=payload)

    async def get(self, action_id: Union[int, str]) -> Action:
        """
        Get an action.
        """
        realm_id = await self._resolve_realm_id()
        if isinstance(action_id, str):
             action_id = await self.client.lookup.get_id(realm_id, "actions", action_id)
             
        response = await self._get(f"/realms/{realm_id}/actions/{action_id}")
        return Action(**response)

    async def update(self, action_id: Union[int, str], name: str) -> Action:
        """
        Update an action.
        """
        realm_id = await self._resolve_realm_id()
        if isinstance(action_id, str):
             action_id = await self.client.lookup.get_id(realm_id, "actions", action_id)
             
        response = await self._put(f"/realms/{realm_id}/actions/{action_id}", json={"name": name})
        self.client.lookup.invalidate(realm_id, "actions")
        return Action(**response)

    async def delete(self, action_id: Union[int, str]) -> Dict[str, Any]:
        """
        Delete an action.
        """
        realm_id = await self._resolve_realm_id()
        if isinstance(action_id, str):
             action_id = await self.client.lookup.get_id(realm_id, "actions", action_id)
             
        return await self._delete(f"/realms/{realm_id}/actions/{action_id}")
