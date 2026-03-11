import logging
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from common.core.redis import RedisClient
from common.models import Realm, Action, ResourceType, AuthRole, PrincipalRoles, Principal
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

class CacheService:

    # Lua script: atomically populate the realm hash only if the key doesn't exist.
    # This prevents a concurrent rebuild from overwriting incremental updates.
    # ARGV[1] = TTL, ARGV[2..N] = field/value pairs.
    _LUA_POPULATE_IF_ABSENT = """
    if redis.call('EXISTS', KEYS[1]) == 0 then
        for i = 2, #ARGV - 1, 2 do
            redis.call('HSET', KEYS[1], ARGV[i], ARGV[i+1])
        end
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
        return 1
    end
    return 0
    """

    # Lua script: atomically update type entries only if the hash is fully populated
    # (indicated by the presence of the '_id' field).
    _LUA_UPDATE_TYPE_IF_EXISTS = """
    if redis.call('HEXISTS', KEYS[1], '_id') == 1 then
        redis.call('HSET', KEYS[1], ARGV[1], ARGV[2], ARGV[3], ARGV[4])
        return 1
    end
    return 0
    """

    @staticmethod
    async def get_realm_map(realm_name: str, db_session: AsyncSession = None) -> dict:
        redis_client = RedisClient.get_instance()
        key = f"realm:{realm_name}"
        data = await redis_client.hgetall(key)
        
        if data:
            return data
            
        # Cache Miss - Populate
        if not db_session:
             raise ValueError(f"Cache miss for realm '{realm_name}' and no DB session provided for refresh")

        async with db_session.begin_nested() if db_session.in_transaction() else db_session:
            # Get Realm with Keycloak Config
            result = await db_session.execute(select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.name == realm_name))
            realm = result.scalars().first()
            
            if not realm:
                raise ValueError(f"Realm '{realm_name}' not found")
                
            mapping = {"_id": str(realm.id)}
            
            # Keycloak Config
            if realm.keycloak_config:
                if realm.keycloak_config.public_key:
                    mapping["_public_key"] = realm.keycloak_config.public_key
                if realm.keycloak_config.algorithm:
                    mapping["_algorithm"] = realm.keycloak_config.algorithm
            
            # Get Actions
            actions = await db_session.execute(select(Action).where(Action.realm_id == realm.id))
            for action in actions.scalars():
                mapping[f"action:{action.name}"] = str(action.id)
                
            # Get ResourceTypes
            r_types = await db_session.execute(select(ResourceType).where(ResourceType.realm_id == realm.id))
            for rt in r_types.scalars():
                mapping[f"type:{rt.name}"] = str(rt.id)
                mapping[f"type_public:{rt.name}"] = str(rt.is_public).lower()
            
            # Get Auth Roles
            roles = await db_session.execute(select(AuthRole).where(AuthRole.realm_id == realm.id))
            for role in roles.scalars():
                mapping[f"role:{role.name}"] = str(role.id)
                
            if mapping:
                # Atomically populate only if key doesn't exist yet.
                # This prevents overwriting incremental updates made by
                # concurrent create/update/delete operations.
                flat_args = []
                for k, v in mapping.items():
                    flat_args.extend([k, v])

                populated = await redis_client.eval(
                    CacheService._LUA_POPULATE_IF_ABSENT,
                    1, key,
                    "3600", *flat_args
                )

                if not populated:
                    # Another process populated or incrementally updated the cache
                    # while we were querying the DB.  Use the existing data.
                    existing = await redis_client.hgetall(key)
                    if existing:
                        return existing
                    # Key was deleted between our eval and hgetall (very rare).
                    # Fall back: write our data unconditionally.
                    await redis_client.hset(key, mapping=mapping)
                    await redis_client.expire(key, 3600)
            
            return mapping

    @staticmethod
    async def invalidate_realm(realm_name: str):
        redis_client = RedisClient.get_instance()
        key = f"realm:{realm_name}"
        await redis_client.delete(key)

    @staticmethod
    async def update_realm_type(
        realm_name: str,
        type_name: str,
        type_id: int,
        is_public: bool = False,
    ):
        """Atomically add or update a single resource type in the cached realm map.

        Uses a Lua script so the update is skipped when the hash has not been
        fully populated yet (no ``_id`` field), preventing creation of an
        incomplete cache entry.  If the hash doesn't exist the entry will be
        included on the next full rebuild triggered by :meth:`get_realm_map`.
        """
        redis_client = RedisClient.get_instance()
        key = f"realm:{realm_name}"
        await redis_client.eval(
            CacheService._LUA_UPDATE_TYPE_IF_EXISTS,
            1,
            key,
            f"type:{type_name}",
            str(type_id),
            f"type_public:{type_name}",
            str(is_public).lower(),
        )

    @staticmethod
    async def remove_realm_type(realm_name: str, type_name: str):
        """Remove a single resource type from the cached realm map.

        ``HDEL`` is atomic and a no-op when the key/field doesn't exist.
        """
        redis_client = RedisClient.get_instance()
        key = f"realm:{realm_name}"
        await redis_client.hdel(key, f"type:{type_name}", f"type_public:{type_name}")

    @staticmethod
    def resolve_ids(realm_map: dict, action_name: str, type_name: str):
        action_id = realm_map.get(f"action:{action_name}")
        type_id = realm_map.get(f"type:{type_name}")
        
        if not action_id or not type_id:
             raise ValueError(f"Action '{action_name}' or Type '{type_name}' not found in realm map")
             
        return int(action_id), int(type_id)
        
    @staticmethod
    def resolve_role_id(realm_map: dict, role_name: str) -> int:
        role_id = realm_map.get(f"role:{role_name}")
        if not role_id:
            return None 
        return int(role_id)

    @staticmethod
    def get_realm_id(realm_map: dict) -> int:
        rid = realm_map.get("_id")
        if not rid:
             raise ValueError("Realm ID not found in map")
        return int(rid)

    @staticmethod
    def get_all_actions(realm_map: dict) -> list[str]:
        """Extract all action names from the realm map."""
        return [
            key.replace("action:", "")
            for key in realm_map.keys()
            if key.startswith("action:")
        ]

    @staticmethod
    async def get_principal_roles(principal_id: int, db_session: AsyncSession = None) -> list[int]:
        if principal_id == 0:
            return []
            
        redis_client = RedisClient.get_instance()
        key = f"principal_roles:{principal_id}"
        data = await redis_client.smembers(key)
        
        if data:
            return [int(role_id) for role_id in data if role_id != "__empty__"]
        
        if not db_session:
             # Cache miss fallback requires DB
             return []

        result = await db_session.execute(
            select(PrincipalRoles.role_id).where(
                PrincipalRoles.principal_id == principal_id
            )
        )
        role_ids = result.scalars().all()
        
        if role_ids:
            await redis_client.sadd(key, *[str(rid) for rid in role_ids])
            await redis_client.expire(key, 3600)
        else:
            await redis_client.sadd(key, "__empty__")
            await redis_client.expire(key, 3600)
        
        return list(role_ids)

    @staticmethod
    async def get_principal(principal_id: int = None, username: str = None, realm_id: int = None, db_session: AsyncSession = None) -> dict | None:
        redis_client = RedisClient.get_instance()
        if principal_id:
            key = f"principal:{principal_id}"
        elif username and realm_id:
            key = f"principal:{realm_id}:{username}"
        else:
            return None
        
        data = await redis_client.get(key)
        
        if data:
            return json.loads(data)
        
        if not db_session:
             return None
        
        if principal_id:
            stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.id == principal_id)
        else:
            stmt = select(Principal).options(selectinload(Principal.roles)).where(
                Principal.username == username,
                Principal.realm_id == realm_id
            )
        
        result = await db_session.execute(stmt)
        principal = result.scalars().first()
        
        if not principal:
            return None
        
        cached = {
            "id": principal.id,
            "username": principal.username,
            "realm_id": principal.realm_id,
            "attributes": principal.attributes or {},
            "role_ids": [r.id for r in principal.roles]
        }
        
        await redis_client.set(f"principal:{principal.id}", json.dumps(cached), ex=3600)
        if principal.username:
            await redis_client.set(f"principal:{principal.realm_id}:{principal.username}", json.dumps(cached), ex=3600)
        
        return cached

    @staticmethod
    async def invalidate_principal(principal_id: int, username: str = None, realm_id: int = None):
        redis_client = RedisClient.get_instance()
        await redis_client.delete(f"principal_roles:{principal_id}")
        await redis_client.delete(f"principal:{principal_id}")
        if username and realm_id:
            await redis_client.delete(f"principal:{realm_id}:{username}")

    @staticmethod
    async def invalidate_principal_roles(principal_id: int):
        redis_client = RedisClient.get_instance()
        await redis_client.delete(f"principal_roles:{principal_id}")
        await redis_client.delete(f"principal:{principal_id}")

    @staticmethod
    async def invalidate_all_principals_for_realm(realm_id: int):
        redis_client = RedisClient.get_instance()
        async for key in redis_client.scan_iter(match="principal_roles:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter(match="principal:*"):
            await redis_client.delete(key)

    @staticmethod
    async def get_external_id_mapping(realm_id: int, type_id: int, external_id: str) -> int | None:
        redis_client = RedisClient.get_instance()
        key = f"extid:{realm_id}:{type_id}:{external_id}"
        cached = await redis_client.get(key)
        if cached:
            return int(cached) if cached != "__none__" else None
        return None
    
    @staticmethod
    async def get_external_id_mappings_batch(realm_id: int, type_id: int, external_ids: list[str]) -> dict[str, int]:
        if not external_ids:
            return {}
        
        redis_client = RedisClient.get_instance()
        pipeline = redis_client.pipeline()
        for ext_id in external_ids:
            key = f"extid:{realm_id}:{type_id}:{ext_id}"
            pipeline.get(key)
        
        results = await pipeline.execute()
        
        mapping = {}
        for ext_id, result in zip(external_ids, results):
            if result and result != "__none__":
                mapping[ext_id] = int(result)
        
        return mapping
    
    @staticmethod
    async def set_external_id_mappings_batch(realm_id: int, type_id: int, mappings: dict[str, int], ttl: int = 3600):
        if not mappings:
            return
        
        redis_client = RedisClient.get_instance()
        pipeline = redis_client.pipeline()
        for ext_id, res_id in mappings.items():
            key = f"extid:{realm_id}:{type_id}:{ext_id}"
            pipeline.set(key, str(res_id), ex=ttl)
        
        await pipeline.execute()
    
    @staticmethod
    async def invalidate_external_id(realm_id: int, type_id: int, external_id: str):
        redis_client = RedisClient.get_instance()
        key = f"extid:{realm_id}:{type_id}:{external_id}"
        await redis_client.delete(key)
    
    @staticmethod
    async def invalidate_external_ids_for_type(realm_id: int, type_id: int):
        redis_client = RedisClient.get_instance()
        pattern = f"extid:{realm_id}:{type_id}:*"
        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
    
    @staticmethod
    async def get_type_level_decision(realm_id: int, principal_id: int, type_id: int, action_id: int, role_ids: list[int]) -> bool | None:
        redis_client = RedisClient.get_instance()
        role_key = ",".join(str(r) for r in sorted(role_ids)) if role_ids else "none"
        key = f"type_decision:{realm_id}:{principal_id}:{type_id}:{action_id}:{role_key}"
        
        cached = await redis_client.get(key)
        if cached is not None:
            return cached == "1"
        return None
    
    @staticmethod
    async def set_type_level_decision(realm_id: int, principal_id: int, type_id: int, action_id: int, role_ids: list[int], decision: bool, ttl: int = 300):
        redis_client = RedisClient.get_instance()
        role_key = ",".join(str(r) for r in sorted(role_ids)) if role_ids else "none"
        key = f"type_decision:{realm_id}:{principal_id}:{type_id}:{action_id}:{role_key}"
        
        await redis_client.set(key, "1" if decision else "0", ex=ttl)
    
    @staticmethod
    async def invalidate_type_decisions_for_principal(realm_id: int, principal_id: int):
        redis_client = RedisClient.get_instance()
        pattern = f"type_decision:{realm_id}:{principal_id}:*"
        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
    
    @staticmethod
    async def invalidate_type_decisions_for_type(realm_id: int, type_id: int):
        redis_client = RedisClient.get_instance()
        pattern = f"type_decision:{realm_id}:*:{type_id}:*"
        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
    
    @staticmethod
    async def invalidate_all_type_decisions(realm_id: int):
        redis_client = RedisClient.get_instance()
        pattern = f"type_decision:{realm_id}:*"
        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
