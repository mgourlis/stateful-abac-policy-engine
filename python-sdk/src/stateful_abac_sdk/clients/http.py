import httpx
import os
import logging
import json
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from .base import IStatefulABACClient
from ..exceptions import AuthenticationError, ApiError

# HTTP Managers
from ..managers.realms import RealmManager
from ..managers.resources import ResourceManager
from ..managers.principals import PrincipalManager
from ..managers.roles import RoleManager
from ..managers.actions import ActionManager
from ..managers.resource_types import ResourceTypeManager
from ..managers.acls import ACLManager
from ..managers.auth import AuthManager
from ..lookup import LookupService
from .. import manifest as manifest_module

logger = logging.getLogger(__name__)

class HTTPStatefulABACClient(IStatefulABACClient):
    """HTTP Implementation of Stateful ABAC Client."""

    def __init__(
        self, 
        base_url: str,
        realm: str = None,
        timeout: float = 30.0,
        **client_kwargs
    ):
        if not base_url:
            raise ValueError("base_url is required for http mode")
        self.base_url = base_url.rstrip('/')
        if not realm:
            raise ValueError("realm is required")
        self.realm = realm
        self.timeout = timeout
        self.client_kwargs = client_kwargs
        self._client: Optional[httpx.AsyncClient] = None
        self._external_client = False # If we allow passing an external client instance later
        self.token = None  # Token is set via set_token() or connect(token=...)

        # Initialize Managers
        self.realms = RealmManager(self)
        self.resources = ResourceManager(self)
        self.principals = PrincipalManager(self)
        self.roles = RoleManager(self)
        self.actions = ActionManager(self)
        self.resource_types = ResourceTypeManager(self)
        self.acls = ACLManager(self)
        self.auth = AuthManager(self)
        
        self.lookup = LookupService(self)
        
        logger.info("StatefulABACClient initialized in HTTP mode")

    @asynccontextmanager
    async def connect(self, token: str = None):
        # Set token first so _get_headers() can use it
        self.set_token(token)
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._get_headers(),
                **self.client_kwargs
            )
        try:
            # Auto-provision realm (create or update config)
            kc_config = None
            from ..config import settings
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
            except ApiError as e:
                # Assuming 404 means not found
                if e.status_code == 404:
                    logger.info(f"Realm '{self.realm}' not found, auto-creating...")
                    await self.realms.create(keycloak_config=kc_config)
                    logger.info(f"Realm '{self.realm}' auto-created.")
                else:
                    raise

            yield self
        finally:
            if not self._external_client and self._client:
                await self._client.aclose()
                self._client = None

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def request(self, method: str, path: str, **kwargs) -> Any:
        """Internal request helper."""
        if not self._client:
            async with httpx.AsyncClient(
                base_url=self.base_url, 
                timeout=self.timeout, 
                headers=self._get_headers(),
                **self.client_kwargs
            ) as temp_client:
                 response = await temp_client.request(method, path, **kwargs)
                 return self._handle_response(response)
        
        response = await self._client.request(method, path, **kwargs)
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code == 401:
            raise AuthenticationError("Invalid or expired token")
        
        if response.is_error:
            try:
                data = response.json()
                detail = data.get("detail", response.text)
            except Exception:
                detail = response.text
            raise ApiError(response.status_code, str(detail), details=getattr(response, 'json', lambda: {})())
            
        try:
            return response.json()
        except Exception:
            return response.text

    def set_token(self, token: str):
        self.token = token
        if self._client:
            self._client.headers["Authorization"] = f"Bearer {token}"

    class ProgressFileReader:
        def __init__(self, f, total_size, logger, log_interval=1024*1024*50):
            self.f = f
            self.total_size = total_size
            self.read_bytes = 0
            self.logger = logger
            self.log_interval = log_interval
            self.last_log = 0
            
        def read(self, size=-1):
            chunk = self.f.read(size)
            self.read_bytes += len(chunk)
            if self.read_bytes - self.last_log >= self.log_interval:
                percent = (self.read_bytes / self.total_size) * 100 if self.total_size > 0 else 0
                self.logger.info(f"Uploading: {self.read_bytes / (1024*1024):.0f} / {self.total_size / (1024*1024):.0f} MB ({percent:.1f}%)")
                self.last_log = self.read_bytes
            
            if not chunk:
                self.logger.info(f"Upload complete ({self.read_bytes / (1024*1024):.0f} MB). Waiting for server response (this may take a few minutes)...")
            
            return chunk

    async def apply_manifest(self, path: str, mode: str = 'update') -> Dict[str, Any]:
        params = {'mode': mode}
        headers = self._get_headers()
        headers.pop("Content-Type", None)
        
        file_size = os.path.getsize(path)
        logger.info(f"Starting upload of {path} ({file_size / (1024*1024):.2f} MB)...")
        
        with open(path, 'rb') as f:
            progress_file = self.ProgressFileReader(f, file_size, logger)
            files = {'file': (os.path.basename(path), progress_file, 'application/json')}
            
            async with httpx.AsyncClient(
                base_url=self.base_url, 
                timeout=self.timeout, 
                headers=headers,
                **self.client_kwargs
            ) as client:
                response = await client.post('/manifest/apply', files=files, params=params)
                
        return self._handle_response(response)

    async def export_manifest(self, realm_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        manifest_data = await manifest_module.export_manifest(self, realm_name)
        
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(manifest_data, f, indent=2)
            logger.info(f"Manifest exported to {output_path}")
        
        return manifest_data
