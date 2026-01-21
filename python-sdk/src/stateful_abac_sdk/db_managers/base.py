"""
Base class for all DB managers.
"""
from typing import TYPE_CHECKING, Union, Optional, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from ..clients.base import IStatefulABACClient


class DBBaseManager:
    """Base class for database-mode managers."""
    
    def __init__(self, db_session: Any, client: Optional["IStatefulABACClient"] = None):
        """
        Initialize the DB manager.
        
        Args:
            db_session: The database session factory.
            client: Optional reference to parent client for cross-manager calls.
        """
        self._db_session = db_session
        self._client = client
    
    @property
    def client(self):
        """Access to the parent client for cross-manager operations."""
        return self._client
    
    def _set_client(self, client):
        """Set the parent client reference (called by StatefulABACClient)."""
        self._client = client
    
    async def _resolve_realm_id(self, realm_id_or_name: Optional[Union[int, str]] = None, session: Optional["AsyncSession"] = None) -> int:
        """
        Resolve a realm name to its ID.
        
        Args:
            realm_id_or_name: Either realm ID (int) or realm name (str)
            session: Optional existing session to use
            
        Returns:
            The realm ID.
        """
        if realm_id_or_name is None:
            if self.client and self.client.realm:
                realm_id_or_name = self.client.realm
            else:
                raise ValueError("Realm ID/Name is required (no default realm set on client)")

        if isinstance(realm_id_or_name, int):
            return realm_id_or_name
        
        from sqlalchemy import select
        from common.models import Realm
        
        async def _do_resolve(s):
            result = await s.execute(
                select(Realm.id).where(Realm.name == realm_id_or_name)
            )
            realm_id = result.scalar_one_or_none()
            if realm_id is None:
                raise ValueError(f"Realm '{realm_id_or_name}' not found")
            return realm_id
        
        if session is not None:
            return await _do_resolve(session)
        else:
            async with self._db_session.get_session() as s:
                return await _do_resolve(s)
    
    async def _resolve_resource_type_id(self, realm_id: int, type_id_or_name: Union[int, str], session: Optional["AsyncSession"] = None) -> int:
        """Resolve resource type ID or name to ID."""
        if isinstance(type_id_or_name, int):
            return type_id_or_name
        
        from sqlalchemy import select
        from common.models import ResourceType
        
        async def _do_resolve(s):
            result = await s.execute(
                select(ResourceType.id).where(
                    ResourceType.realm_id == realm_id,
                    ResourceType.name == type_id_or_name
                )
            )
            type_id = result.scalar_one_or_none()
            if type_id is None:
                raise ValueError(f"ResourceType '{type_id_or_name}' not found in realm {realm_id}")
            return type_id
        
        if session is not None:
            return await _do_resolve(session)
        else:
            async with self._db_session.get_session() as s:
                return await _do_resolve(s)
    
    async def _resolve_action_id(self, realm_id: int, action_id_or_name: Union[int, str], session: Optional["AsyncSession"] = None) -> int:
        """Resolve action ID or name to ID."""
        if isinstance(action_id_or_name, int):
            return action_id_or_name
        
        from sqlalchemy import select
        from common.models import Action
        
        async def _do_resolve(s):
            result = await s.execute(
                select(Action.id).where(
                    Action.realm_id == realm_id,
                    Action.name == action_id_or_name
                )
            )
            act_id = result.scalar_one_or_none()
            if act_id is None:
                raise ValueError(f"Action '{action_id_or_name}' not found in realm {realm_id}")
            return act_id
        
        if session is not None:
            return await _do_resolve(session)
        else:
            async with self._db_session.get_session() as s:
                return await _do_resolve(s)
    
    async def _resolve_principal_id(self, realm_id: int, principal_id_or_name: Union[int, str], session: Optional["AsyncSession"] = None) -> int:
        """Resolve principal ID or username to ID."""
        if isinstance(principal_id_or_name, int):
            return principal_id_or_name
        
        from sqlalchemy import select
        from common.models import Principal
        
        async def _do_resolve(s):
            result = await s.execute(
                select(Principal.id).where(
                    Principal.realm_id == realm_id,
                    Principal.username == principal_id_or_name
                )
            )
            pid = result.scalar_one_or_none()
            if pid is None:
                raise ValueError(f"Principal '{principal_id_or_name}' not found in realm {realm_id}")
            return pid
        
        if session is not None:
            return await _do_resolve(session)
        else:
            async with self._db_session.get_session() as s:
                return await _do_resolve(s)
    
    async def _resolve_role_id(self, realm_id: int, role_id_or_name: Union[int, str], session: Optional["AsyncSession"] = None) -> int:
        """Resolve role ID or name to ID."""
        if isinstance(role_id_or_name, int):
            return role_id_or_name
        
        from sqlalchemy import select
        from common.models import AuthRole
        
        async def _do_resolve(s):
            result = await s.execute(
                select(AuthRole.id).where(
                    AuthRole.realm_id == realm_id,
                    AuthRole.name == role_id_or_name
                )
            )
            rid = result.scalar_one_or_none()
            if rid is None:
                raise ValueError(f"Role '{role_id_or_name}' not found in realm {realm_id}")
            return rid
        
        if session is not None:
            return await _do_resolve(session)
        else:
            async with self._db_session.get_session() as s:
                return await _do_resolve(s)
