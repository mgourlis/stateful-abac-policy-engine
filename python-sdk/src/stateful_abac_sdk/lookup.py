
from typing import Dict, Optional, Tuple, TYPE_CHECKING
import time

if TYPE_CHECKING:
    from .client import StatefulABACClient

class LookupService:
    def __init__(self, client: "StatefulABACClient"):
        self.client = client
        # Cache Structure:
        # {
        #    realm_id: { ... }, (Per Realm)
        #    "_global": {
        #        "realms": { "name": id, ... }
        #    }
        # }
        self._cache: Dict[str, Dict] = {"_global": {"realms": {}, "timestamp": 0}}
        self._ttl = 60.0 # Cache TTL in seconds

    def _get_cache(self, realm_id: int) -> Dict:
        now = time.time()
        if realm_id not in self._cache:
            self._cache[realm_id] = {
                "resource_types": {},
                "actions": {},
                "roles": {},
                "principals": {},
                "timestamp": 0
            }
        return self._cache[realm_id]

    async def _refresh_realm_cache(self):
        # Refresh global realm list? or just try to get one?
        # Since we don't have a "List All Realms" easily accessible/efficient for everyone (maybe?), 
        # using the `get` method by name is better if we miss.
        # But we want to cache it.
        # Actually `client.realms.get(name)` works.
        pass

    async def get_realm_id(self, name: str) -> int:
        """Resolve Realm Name to ID."""
        if not name: raise ValueError("Realm name required")
        
        # Check cache
        g_cache = self._cache["_global"]
        if name in g_cache["realms"]:
            return g_cache["realms"][name]
            
        # Fetch from API
        # Direct API call to resolve realm name to ID
        # We assume GET /realms/name/{name} returns the realm details including ID
        # This avoids using client.realms.get() which is scoped to client.realm
        response = await self.client.request("GET", f"/realms/name/{name}")
        realm_id = response['id']
        g_cache["realms"][name] = realm_id
        return realm_id

    def invalidate(self, realm_id: int, entity_type: str):
        """Invalidate the cache for a specific entity type in a realm."""
        if realm_id in self._cache:
            # We just empty the dict for that entity type
            # This forces a refresh on next read
            if entity_type in self._cache[realm_id]:
               self._cache[realm_id][entity_type] = {}
               
    def invalidate_realm(self, name: str):
        """Invalidate a realm name mapping."""
        g_cache = self._cache["_global"]
        if name in g_cache["realms"]:
            del g_cache["realms"][name]

    async def _refresh_cache_if_needed(self, realm_id: int, entity_type: str):
        cache = self._get_cache(realm_id)
        now = time.time()
        
        # Simple TTL check per realm (could be per entity type, but kept simple)
        if cache["timestamp"] + self._ttl > now and cache[entity_type]:
            return

        # Fetch and Populate
        # Fetch and Populate
        if entity_type == "resource_types":
            # items = await self.client.resource_types.list(realm_id)
            response = await self.client.request("GET", f"/realms/{realm_id}/resource-types")
            cache["resource_types"] = {r["name"]: r["id"] for r in response}
            
        elif entity_type == "actions":
            # items = await self.client.actions.list(realm_id) 
            response = await self.client.request("GET", f"/realms/{realm_id}/actions")
            cache["actions"] = {r["name"]: r["id"] for r in response}
            
        elif entity_type == "roles":
            # items = await self.client.roles.list(realm_id)
            response = await self.client.request("GET", f"/realms/{realm_id}/roles")
            cache["roles"] = {r["name"]: r["id"] for r in response}
            
        elif entity_type == "principals":
            # items = await self.client.principals.list(realm_id)
            response = await self.client.request("GET", f"/realms/{realm_id}/principals")
            cache["principals"] = {r["username"]: r["id"] for r in response}
            
        cache["timestamp"] = now

    async def get_id(self, realm_id: int, entity_type: str, name: str) -> int:
        """
        Resolve a name to an ID.
        entity_type: "resource_types", "actions", "roles", "principals"
        """
        if not name:
            raise ValueError(f"Name cannot be empty for {entity_type}")
            
        await self._refresh_cache_if_needed(realm_id, entity_type)
        
        cache = self._get_cache(realm_id)
        mapping = cache.get(entity_type, {})
        
        if name not in mapping:
            # Try FORCE refresh once if missed
            # Reset timestamp to force fetch
            cache["timestamp"] = 0
            await self._refresh_cache_if_needed(realm_id, entity_type)
            mapping = cache.get(entity_type, {})
            
        if name not in mapping:
            raise ValueError(f"Could not resolve {entity_type} name: '{name}' in realm {realm_id}")
            
        return mapping[name]
