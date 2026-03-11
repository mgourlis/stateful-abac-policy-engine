import logging
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from common.models import Realm, RealmKeycloakConfig, AuthRole, Principal, PrincipalRoles
from common.adapters.keycloak_adapter import KeycloakAdapter

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def sync_realm(self, realm_id: int):
        """
        Syncs roles and principals from Keycloak to the local Realm.
        """
        logger.info(f"Starting sync for realm_id: {realm_id}")
        
        # Fetch Realm with Config
        stmt = select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.id == realm_id)
        result = await self.session.execute(stmt)
        realm = result.scalar_one_or_none()

        if not realm:
            logger.error(f"Realm with id {realm_id} not found.")
            return

        if not realm.keycloak_config:
            logger.warning(f"Realm {realm.name} has no Keycloak configuration. Skipping sync.")
            return

        adapter = KeycloakAdapter(realm.keycloak_config)
        
        # Run synchronous Keycloak calls in a separate thread to avoid blocking the async loop
        try:
            loop = asyncio.get_running_loop()
            roles = await loop.run_in_executor(None, adapter.get_roles)
            
            groups = []
            if realm.keycloak_config.sync_groups:
                groups = await loop.run_in_executor(None, adapter.get_groups)
                
            users = await loop.run_in_executor(None, adapter.get_principals)
        except Exception as e:
            logger.error(f"Failed to fetch data from Keycloak: {e}")
            return

        # Sync Roles
        await self._sync_roles(realm, roles)
        
        # Sync Groups as Roles
        if groups:
            await self._sync_roles(realm, groups)
        
        # Sync Principals (Users)
        await self._sync_principals(realm, users, roles, adapter)

        try:
            await self.session.commit()
            logger.info(f"Sync completed successfully for realm: {realm.name}")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to commit sync changes: {e}")

    async def _sync_roles(self, realm: Realm, keycloak_roles: List[Dict[str, Any]]):
        """
        Syncs Keycloak roles (or groups) to Realm roles.
        Strategy: Create missing, Update existing.
        """
        existing_roles_stmt = select(AuthRole).where(AuthRole.realm_id == realm.id)
        result = await self.session.execute(existing_roles_stmt)
        existing_roles = {r.name: r for r in result.scalars().all()}

        for k_role in keycloak_roles:
            role_name = k_role.get("name")
            if not role_name:
                continue
                
            attributes = k_role.get("attributes", {})
            
            if role_name in existing_roles:
                # Update
                role = existing_roles[role_name]
                role.attributes = attributes
            else:
                # Create
                new_role = AuthRole(
                    name=role_name,
                    realm_id=realm.id,
                    attributes=attributes
                )
                self.session.add(new_role)
                existing_roles[role_name] = new_role

    async def _sync_principals(self, realm: Realm, keycloak_users: List[Dict[str, Any]], keycloak_roles: List[Dict[str, Any]], adapter: KeycloakAdapter):
        """
        Syncs Keycloak users to Realm Principals.
        Also syncs role (and group) assignments.
        """
        # Fetch existing principals
        existing_principals_stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.realm_id == realm.id)
        result = await self.session.execute(existing_principals_stmt)
        existing_principals = {p.username: p for p in result.scalars().all()}

        # Fetch all roles to map name -> Role object
        all_roles_stmt = select(AuthRole).where(AuthRole.realm_id == realm.id)
        result = await self.session.execute(all_roles_stmt)
        all_roles_map = {r.name: r for r in result.scalars().all()}
        
        loop = asyncio.get_running_loop()

        for k_user in keycloak_users:
            username = k_user.get("username")
            user_id = k_user.get("id")
            if not username or not user_id:
                continue

            attributes = k_user.get("attributes", {})
            for field in ["email", "firstName", "lastName", "emailVerified", "enabled"]:
                if field in k_user:
                    attributes[field] = k_user[field]
            
            principal = None
            if username in existing_principals:
                principal = existing_principals[username]
                principal.attributes = attributes
            else:
                principal = Principal(
                    username=username,
                    realm_id=realm.id,
                    attributes=attributes
                )
                self.session.add(principal)
                existing_principals[username] = principal
            
            # Sync Roles/Groups for this user
            try:
                # Run in executor to avoid blocking
                user_roles_data = await loop.run_in_executor(None, lambda: adapter.get_user_roles(user_id))
                
                user_groups_data = []
                if realm.keycloak_config.sync_groups:
                    user_groups_data = await loop.run_in_executor(None, lambda: adapter.get_user_groups(user_id))
                
                # Combine User Roles and User Groups
                current_roles = []
                seen_roles = set()
                
                # Process Roles
                for ur in user_roles_data:
                    r_name = ur.get("name")
                    if r_name in all_roles_map and r_name not in seen_roles:
                        current_roles.append(all_roles_map[r_name])
                        seen_roles.add(r_name)
                
                # Process Groups
                for ug in user_groups_data:
                    g_name = ug.get("name")
                    if g_name in all_roles_map and g_name not in seen_roles:
                        current_roles.append(all_roles_map[g_name])
                        seen_roles.add(g_name)
                
                # SQLAlchemy collection replacement
                principal.roles = current_roles
                
            except Exception as e:
                logger.error(f"Failed to sync roles for user {username}: {e}")
