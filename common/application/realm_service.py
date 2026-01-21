from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from sqlalchemy.orm import selectinload
from apscheduler.triggers.cron import CronTrigger

from common.models import Realm, RealmKeycloakConfig, ExternalID, ACL, Resource, PrincipalRoles, AuthRole, Principal, Action, ResourceType
from common.schemas.realm_api import RealmCreate, RealmUpdate
from common.services.cache import CacheService

class RealmService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_realm(self, realm_in: RealmCreate) -> Realm:
        # Check if exists
        stmt = select(Realm).where(Realm.name == realm_in.name)
        existing = await self.session.execute(stmt)
        if existing.scalar_one_or_none():
            raise ValueError("Realm with this name already exists")
        
        realm = Realm(
            name=realm_in.name,
            description=realm_in.description,
            is_active=realm_in.is_active
        )
        self.session.add(realm)
        await self.session.commit()
        await self.session.refresh(realm)
        
        if realm_in.keycloak_config:
            config_in = realm_in.keycloak_config
            
            # Validate cron if present (just check, don't schedule here)
            if getattr(config_in, "sync_cron", None):
                try:
                    CronTrigger.from_crontab(config_in.sync_cron)
                except Exception:
                     pass # Ignore or log invalid cron

            config = RealmKeycloakConfig(
                realm_id=realm.id,
                server_url=config_in.server_url,
                keycloak_realm=config_in.keycloak_realm,
                client_id=config_in.client_id,
                client_secret=config_in.client_secret,
                verify_ssl=config_in.verify_ssl,
                settings=config_in.settings,
                sync_cron=config_in.sync_cron,
                sync_groups=config_in.sync_groups,
                public_key=config_in.public_key,
                algorithm=config_in.algorithm
            )
            self.session.add(config)
            await self.session.commit()
            
        # Create Partitions
        try:
            rid = realm.id
            await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS resource_{rid} PARTITION OF resource FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
            await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS acl_{rid} PARTITION OF acl FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
            await self.session.execute(text(f"CREATE TABLE IF NOT EXISTS external_ids_{rid} PARTITION OF external_ids FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
            await self.session.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to create realm partitions: {e}")

        # Re-fetch with config
        stmt = select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.id == realm.id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_realm(self, realm_id: int) -> Optional[Realm]:
        stmt = select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.id == realm_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_realm_by_name(self, name: str) -> Optional[Realm]:
        stmt = select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_realms(self) -> List[Realm]:
        """List all realms."""
        stmt = select(Realm).options(selectinload(Realm.keycloak_config))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_realm(self, realm_id: int, realm_in: RealmUpdate) -> Optional[Realm]:
        realm = await self.get_realm(realm_id)
        if not realm:
            return None

        if realm_in.name is not None and realm_in.name != realm.name:
            await CacheService.invalidate_realm(realm.name)
            realm.name = realm_in.name
            
        if realm_in.description is not None:
            realm.description = realm_in.description
        
        if realm_in.keycloak_config:
            config_in = realm_in.keycloak_config
            if realm.keycloak_config:
                update_data = config_in.model_dump(exclude_unset=True)
                for field, value in update_data.items():
                    if field != "sync_cron":
                        setattr(realm.keycloak_config, field, value)
                    else:
                        # Validate cron
                         if value and isinstance(value, str) and value.strip():
                             try:
                                 CronTrigger.from_crontab(value)
                                 realm.keycloak_config.sync_cron = value
                             except Exception:
                                 pass
                         else:
                             realm.keycloak_config.sync_cron = None
            else:
                # Create new
                if not (config_in.server_url and config_in.keycloak_realm and config_in.client_id):
                     raise ValueError("Missing required fields for creating new Keycloak config")
                
                new_config = RealmKeycloakConfig(
                    realm_id=realm.id,
                    **config_in.model_dump(exclude_unset=True)
                )
                self.session.add(new_config)
                # Ensure relationship is updated on object for immediate use if needed logic depends on it
                realm.keycloak_config = new_config

        await self.session.commit()
        await self.session.refresh(realm)
        await CacheService.invalidate_realm(realm.name)
        return realm

    async def delete_realm(self, realm_id: int) -> bool:
        realm = await self.get_realm(realm_id)
        if not realm:
            return False
        
        # Delete Resource Types via Service (cleans up their partitions)
        from .resource_type_service import ResourceTypeService
        rt_service = ResourceTypeService(self.session)
        
        # Get all resource types
        stmt = select(ResourceType.id).where(ResourceType.realm_id == realm_id)
        rt_ids = (await self.session.execute(stmt)).scalars().all()
        
        for rt_id in rt_ids:
            await rt_service.delete_resource_type(realm_id, rt_id)

        # Drop Partitions
        try:
             await self.session.execute(text(f"DROP TABLE IF EXISTS resource_{realm_id} CASCADE"))
             await self.session.execute(text(f"DROP TABLE IF EXISTS acl_{realm_id} CASCADE"))
             await self.session.execute(text(f"DROP TABLE IF EXISTS external_ids_{realm_id} CASCADE"))
        except Exception as e:
             # Log but proceed
             pass
        
        # Manual Cascade
        await self.session.execute(delete(ExternalID).where(ExternalID.realm_id == realm_id))
        await self.session.execute(delete(ACL).where(ACL.realm_id == realm_id))
        await self.session.execute(delete(Resource).where(Resource.realm_id == realm_id))
        
        p_stmt = select(Principal.id).where(Principal.realm_id == realm_id)
        await self.session.execute(delete(PrincipalRoles).where(PrincipalRoles.principal_id.in_(p_stmt)))
        
        await self.session.execute(delete(AuthRole).where(AuthRole.realm_id == realm_id))
        await self.session.execute(delete(Principal).where(Principal.realm_id == realm_id))
        await self.session.execute(delete(Action).where(Action.realm_id == realm_id))
        await self.session.execute(delete(ResourceType).where(ResourceType.realm_id == realm_id))
        await self.session.execute(delete(RealmKeycloakConfig).where(RealmKeycloakConfig.realm_id == realm_id))
        
        

        await self.session.delete(realm)
        await self.session.commit()
        
        await CacheService.invalidate_realm(realm.name)
        return True
