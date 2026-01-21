"""
SDK Configuration - extends common config with SDK-specific settings.
"""
import os
from typing import Optional
from common.core.config import Config as BaseConfig


class SDKConfig(BaseConfig):
    """SDK-specific configuration that extends the base common config."""
    
    @property
    def MODE(self) -> str:
        """Client mode: 'http' or 'db'."""
        return os.getenv("STATEFUL_ABAC_CLIENT_MODE", "http")
    
    @property
    def BASE_URL(self) -> Optional[str]:
        """Base URL for HTTP mode."""
        return os.getenv("STATEFUL_ABAC_CLIENT_BASE_URL")

    @property
    def REALM(self) -> Optional[str]:
        """Default realm name/ID for the client."""
        return os.getenv("STATEFUL_ABAC_REALM")

    @property
    def KEYCLOAK_SERVER_URL(self) -> Optional[str]:
        return os.getenv("STATEFUL_ABAC_KEYCLOAK_SERVER_URL")

    @property
    def KEYCLOAK_REALM(self) -> Optional[str]:
        return os.getenv("STATEFUL_ABAC_KEYCLOAK_REALM")

    @property
    def KEYCLOAK_CLIENT_ID(self) -> Optional[str]:
        return os.getenv("STATEFUL_ABAC_KEYCLOAK_CLIENT_ID")

    @property
    def KEYCLOAK_CLIENT_SECRET(self) -> Optional[str]:
        return os.getenv("STATEFUL_ABAC_KEYCLOAK_CLIENT_SECRET")

    @property
    def KEYCLOAK_SYNC_CRON(self) -> Optional[str]:
        return os.getenv("STATEFUL_ABAC_KEYCLOAK_SYNC_CRON")
    
    @property
    def KEYCLOAK_SYNC_GROUPS(self) -> bool:
        val = os.getenv("STATEFUL_ABAC_KEYCLOAK_SYNC_GROUPS", "false").lower()
        return val in ("true", "1", "yes")

    @property
    def KEYCLOAK_VERIFY_SSL(self) -> bool:
        val = os.getenv("STATEFUL_ABAC_KEYCLOAK_VERIFY_SSL", "true").lower()
        return val in ("true", "1", "yes")

settings = SDKConfig()
