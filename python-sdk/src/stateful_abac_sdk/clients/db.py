from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, AsyncGenerator
import logging
import asyncio

from .base import IStatefulABACClient
from ..db_managers import (
    DBRealmManager, DBResourceManager, DBResourceTypeManager,
    DBPrincipalManager, DBRoleManager, DBActionManager,
    DBACLManager, DBAuthManager
)
from common.application.manifest_service import ManifestService
from common.core.database import AsyncSessionLocal
from common.worker import SchedulerWorker
from common.core.config import settings

logger = logging.getLogger(__name__)

class CommonDBSessionAdapter:
    """
    Adapter to make common.core.database compatible with SDK managers.
    Replicates the transaction management of the original DBSession.
    """
    
    def __init__(self):
        self._session_factory = AsyncSessionLocal
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator:
        """
        Get an async session with automatic transaction management.
        """
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def close(self):
        """
        Common database engine is global/singleton, so we generally don't dispose it 
        here unless we own the lifecycle. For compatibility, this is a no-op 
        or could handle cleanup if needed.
        """
        pass

class DBStatefulABACClient(IStatefulABACClient):
    """Database Direct Implementation of Stateful ABAC Client."""

    def __init__(self, realm: str = None):
        """
        Initialize the DB Client.
        
        Configuration is loaded from common.core.config.settings (env vars).
        Scheduler is controlled by STATEFUL_ABAC_ENABLE_SCHEDULER env var.
        """
        self._worker: Optional[SchedulerWorker] = None
        self._audit_task = None
        if not realm:
            raise ValueError("realm is required")
        self.realm = realm
        
        # We use the CommonDBSessionAdapter which relies on the global common configuration
        self._db_session = CommonDBSessionAdapter()

        self.realms = DBRealmManager(self._db_session)
        self.resources = DBResourceManager(self._db_session)
        self.resource_types = DBResourceTypeManager(self._db_session)
        self.principals = DBPrincipalManager(self._db_session)
        self.roles = DBRoleManager(self._db_session)
        self.actions = DBActionManager(self._db_session)
        self.acls = DBACLManager(self._db_session)
        self.auth = DBAuthManager(self._db_session, self)

        # Set client references
        for manager in [self.realms, self.resources, self.resource_types,
                       self.principals, self.roles, self.actions,
                       self.acls]:
            manager._set_client(self)
        
        self.lookup = None # Not needed/available to user directly in DB mode usually
        
        
        logger.info("StatefulABACClient initialized in DB mode using Common Database")

    def set_token(self, token: str):
        """Set the authentication token (mirrors HTTP client API)."""
        self.token = token

    @asynccontextmanager
    async def connect(self, token: str):
        """
        Connect and start background services (scheduler, audit queue).
        Mirrors the FastAPI lifespan behavior from app/main.py.
        """
        # Start audit queue processor
        from common.services.audit import process_audit_queue
        self._audit_task = asyncio.create_task(process_audit_queue(AsyncSessionLocal))
        
        # Start scheduler if enabled (via STATEFUL_ABAC_ENABLE_SCHEDULER env var)
        if settings.ENABLE_SCHEDULER and not settings.TESTING:
            self._worker = SchedulerWorker()
            await self._worker.start_scheduler()
            logger.info("Scheduler worker started")
        
        try:
            self.set_token(token)
            
            # Auto-provision realm (create or update config)
            kc_config = None
            if settings.KEYCLOAK_SERVER_URL and settings.KEYCLOAK_REALM and settings.KEYCLOAK_CLIENT_ID:
                from ..models import RealmKeycloakConfig
                kc_config = RealmKeycloakConfig(
                    server_url=settings.KEYCLOAK_SERVER_URL,
                    keycloak_realm=settings.KEYCLOAK_REALM,
                    client_id=settings.KEYCLOAK_CLIENT_ID,
                    client_secret=settings.KEYCLOAK_CLIENT_SECRET,
                    sync_cron=settings.KEYCLOAK_SYNC_CRON,
                    sync_groups=settings.KEYCLOAK_SYNC_GROUPS,
                    verify_ssl=settings.KEYCLOAK_VERIFY_SSL
                )

            try:
                await self.realms.get()
                # Realm exists, update config if present
                if kc_config:
                    logger.info(f"Realm '{self.realm}' found, updating Keycloak config...")
                    await self.realms.update(keycloak_config=kc_config)
            except ValueError:
                logger.info(f"Realm '{self.realm}' not found, auto-creating...")
                await self.realms.create(keycloak_config=kc_config)
                logger.info(f"Realm '{self.realm}' auto-created.")

            yield self
        finally:
            # Close Redis connection first
            from common.core.redis import RedisClient
            await RedisClient.close()
            
            # Stop scheduler
            if self._worker:
                await self._worker.stop_scheduler()
                logger.info("Scheduler worker stopped")
            
            # Stop audit task
            if self._audit_task:
                self._audit_task.cancel()
                try:
                    await self._audit_task
                except asyncio.CancelledError:
                    pass

    async def close(self):
        """Close connections including Redis."""
        # Close Redis connection first
        from common.core.redis import RedisClient
        await RedisClient.close()
        
        if self._db_session:
            await self._db_session.close()

    async def apply_manifest(self, path: str, mode: str = 'update') -> Dict[str, Any]:
        """Apply manifest directly to DB."""
        async with self._db_session.get_session() as session:
            # We can pass path string directly as ManifestService handles file loading
            result = await ManifestService.apply_manifest(session, path, mode=mode)
            return result

    async def export_manifest(self, realm_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Export manifest directly from DB."""
        async with self._db_session.get_session() as session:
            manifest_data = await ManifestService.export_manifest(session, realm_name)
            
            if output_path:
                import json
                with open(output_path, 'w') as f:
                    json.dump(manifest_data, f, indent=2)
                logger.info(f"Manifest exported to {output_path}")
            
            return manifest_data
