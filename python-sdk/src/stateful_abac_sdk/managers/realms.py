from typing import Dict, Any, List, Optional, Union
from ..models import Realm, RealmKeycloakConfig
from .base import BaseManager
from ..interfaces import IRealmManager

class RealmManager(BaseManager, IRealmManager):
    async def create(self, description: Optional[str] = None, keycloak_config: Optional[RealmKeycloakConfig] = None) -> Realm:
        """
        Create a new realm using the client's configured realm name.
        
        Args:
            description: Optional description.
            keycloak_config: Optional Keycloak configuration object.

        Returns:
            The created Realm object.
        """
        if not self.client.realm:
            raise ValueError("Client must be initialized with a realm to use create()")
            
        data = {"name": self.client.realm}
        if description:
            data["description"] = description
        if keycloak_config:
            data["keycloak_config"] = keycloak_config.model_dump()
            
        response = await self._post("/realms", json=data)
        realm = Realm(**response)
        return realm

    async def update(
        self, 
        description: Optional[str] = None,
        keycloak_config: Optional[RealmKeycloakConfig] = None
    ) -> Realm:
        """
        Update the current realm.
        """
        realm_id = await self._resolve_realm_id()
        data = {}
        if description:
            data["description"] = description
        if keycloak_config:
            data["keycloak_config"] = keycloak_config.model_dump()
            
        response = await self._put(f"/realms/{realm_id}", json=data)
        
        realm = Realm(**response)
        return realm

    async def get(self) -> Realm:
        """
        Get the current realm.
        """
        realm_id = await self._resolve_realm_id()
        response = await self._get(f"/realms/{realm_id}")
        return Realm(**response)

    async def delete(self) -> Dict[str, Any]:
        """
        Delete the current realm.
        """
        realm_id = await self._resolve_realm_id()
        return await self._delete(f"/realms/{realm_id}")

    # list is already correct (no args)

    async def sync(self) -> Dict[str, Any]:
        """
        Trigger Keycloak sync for the current realm.
        """
        realm_id = await self._resolve_realm_id()
        return await self._post(f"/realms/{realm_id}/sync")
