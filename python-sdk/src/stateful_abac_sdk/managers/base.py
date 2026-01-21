from typing import TYPE_CHECKING, List, Dict, Any, Optional, Union

if TYPE_CHECKING:
    from ..client import StatefulABACClient

class BaseManager:
    def __init__(self, client: "StatefulABACClient"):
        self.client = client
        
    async def _resolve_realm_id(self, realm_id_or_name: Optional[Union[int, str]] = None) -> int:
        """Resolve Realm Name to ID if needed."""
        if realm_id_or_name is None:
            if self.client.realm:
                realm_id_or_name = self.client.realm
            else:
                raise ValueError("Realm ID/Name is required (no default realm set on client)")

        if isinstance(realm_id_or_name, int):
            return realm_id_or_name
        return await self.client.lookup.get_realm_id(realm_id_or_name)
        
    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a GET request.

        Args:
            path: The API path.
            params: Optional query parameters.

        Returns:
            The JSON response.
        """
        return await self.client.request("GET", path, params=params)
        
    async def _post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a POST request.

        Args:
            path: The API path.
            json: Optional JSON body.

        Returns:
            The JSON response.
        """
        return await self.client.request("POST", path, json=json)
        
    async def _put(self, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a PUT request.

        Args:
            path: The API path.
            json: Optional JSON body.

        Returns:
            The JSON response.
        """
        return await self.client.request("PUT", path, json=json)
        
    async def _delete(self, path: str) -> Any:
        """
        Execute a DELETE request.

        Args:
            path: The API path.

        Returns:
            The JSON response.
        """
        return await self.client.request("DELETE", path)
