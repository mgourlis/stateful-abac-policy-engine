from typing import List, Dict, Any, Optional, Union
import asyncio
from .base import DBBaseManager
from common.models import Realm as RealmModel
from ..models import Realm, RealmKeycloakConfig
from ..interfaces import IRealmManager
from common.application.realm_service import RealmService
from common.schemas.realm_api import RealmCreate, RealmUpdate


class DBRealmManager(DBBaseManager, IRealmManager):
    """DB-mode manager for realm operations."""
    
    async def create(
        self, 
        description: Optional[str] = None,
        keycloak_config: Optional[RealmKeycloakConfig] = None
    ) -> Realm:
        """Create a new realm using the client's configured realm name."""
        if not self.client.realm:
            raise ValueError("Client must be initialized with a realm to use create()")
            
        async with self._db_session.get_session() as session:
            service = RealmService(session)
            
            kc_config_dict = None
            if keycloak_config:
                kc_config_dict = keycloak_config.model_dump(exclude_unset=True)
            
            realm_create = RealmCreate(
                name=self.client.realm,
                description=description,
                is_active=True,
                keycloak_config=kc_config_dict
            )
            
            created_realm = await service.create_realm(realm_create)
            
            # Trigger initial sync if configured (like API endpoint does)
            if created_realm.keycloak_config and created_realm.keycloak_config.sync_cron:
                asyncio.create_task(self._run_sync_task(created_realm.id))
            
            return self._map_realm(created_realm)
    
    async def update(
        self, 
        description: Optional[str] = None,
        keycloak_config: Optional[RealmKeycloakConfig] = None
    ) -> Realm:
        """Update the current realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = RealmService(session)
            
            kc_config_dict = None
            if keycloak_config:
                kc_config_dict = keycloak_config.model_dump(exclude_unset=True)

            realm_update = RealmUpdate(
                name=None, # Name update not allowed via this method anymore as per interface
                description=description,
                keycloak_config=kc_config_dict
            )
            
            updated_realm = await service.update_realm(realm_id_int, realm_update)
            
            if updated_realm is None:
                 raise ValueError(f"Realm '{self.client.realm}' not found")

            # self.client.realm remains the same
            return self._map_realm(updated_realm)
    
    async def get(self) -> Realm:
        """Get the current realm."""
        async with self._db_session.get_session() as session:
            service = RealmService(session)
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            realm = await service.get_realm(realm_id_int)
            
            if realm is None:
                raise ValueError(f"Realm '{self.client.realm}' not found")
            
            return self._map_realm(realm)
    
    async def delete(self) -> Dict[str, Any]:
        """Delete the current realm."""
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = RealmService(session)
            success = await service.delete_realm(realm_id_int)
            
            if not success:
               raise ValueError(f"Realm '{self.client.realm}' not found")
            
            return {"status": "deleted"}
    
    async def list(self) -> List[Realm]:
        """List all realms."""
        async with self._db_session.get_session() as session:
            service = RealmService(session)
            realms = await service.list_realms()
            
            return [self._map_realm(r) for r in realms]
    
    async def sync(self) -> Dict[str, Any]:
        """
        Trigger Keycloak sync for the current realm.
        """
        async with self._db_session.get_session() as session:
            realm_id_int = await self._resolve_realm_id(self.client.realm, session=session)
            service = RealmService(session)
            realm = await service.get_realm(realm_id_int)
            
            if not realm:
                raise ValueError(f"Realm '{self.client.realm}' not found")
            
            # Fire background sync task
            asyncio.create_task(self._run_sync_task(realm_id_int))
            
            return {"status": "sync_started"}
    
    def _map_realm(self, realm_orm) -> Realm:
        """Map ORM Realm (with keycloak_config) to SDK Realm model."""
        kc_config = None
        if realm_orm.keycloak_config:
            kc = realm_orm.keycloak_config
            kc_config = RealmKeycloakConfig(
                server_url=kc.server_url,
                keycloak_realm=kc.keycloak_realm,
                client_id=kc.client_id,
                client_secret=kc.client_secret,
                verify_ssl=kc.verify_ssl,
                public_key=kc.public_key,
                algorithm=kc.algorithm,
                settings=kc.settings,
                sync_cron=kc.sync_cron,
                sync_groups=kc.sync_groups
            )
        
        return Realm(
            id=realm_orm.id,
            name=realm_orm.name,
            description=realm_orm.description,
            is_active=realm_orm.is_active,
            keycloak_config=kc_config
        )
    
    async def _run_sync_task(self, realm_id: int):
        """Run Keycloak sync as background task (like API endpoint's self_run_sync_task)."""
        from common.services.sync_service import SyncService
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info(f"Starting initial Keycloak sync for Realm ID: {realm_id}")
        
        async with self._db_session.get_session() as session:
            try:
                service = SyncService(session)
                await service.sync_realm(realm_id)
                logger.info(f"Keycloak sync completed for Realm ID: {realm_id}")
            except Exception as e:
                logger.error(f"Error during Keycloak sync for Realm {realm_id}: {e}")
