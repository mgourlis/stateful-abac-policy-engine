"""
Configuration schema definitions using Pydantic.

Defines the YAML configuration structure for the sync tool.
"""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, Field
import os
import re


def expand_env_vars(value: str) -> str:
    """Expand ${VAR} patterns in string with environment variable values."""
    pattern = r'\$\{([^}]+)\}'
    
    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))
    
    return re.sub(pattern, replacer, value)


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    type: Literal["postgresql"] = "postgresql"
    host: str = "localhost"
    port: int = 5432
    database: str
    user: str
    password: str = ""
    
    def model_post_init(self, __context):
        """Expand environment variables in password."""
        if self.password:
            object.__setattr__(self, 'password', expand_env_vars(self.password))


class KeycloakConfig(BaseModel):
    """Keycloak integration configuration."""
    server_url: str
    keycloak_realm: str
    client_id: str
    client_secret: Optional[str] = None
    verify_ssl: bool = True
    sync_cron: Optional[str] = None
    sync_groups: bool = False
    public_key: Optional[str] = None
    algorithm: str = "RS256"
    settings: Optional[Dict[str, Any]] = None
    
    def model_post_init(self, __context):
        """Expand environment variables in secrets."""
        if self.client_secret:
            object.__setattr__(self, 'client_secret', expand_env_vars(self.client_secret))
        if self.public_key:
            object.__setattr__(self, 'public_key', expand_env_vars(self.public_key))


class RealmConfig(BaseModel):
    """Realm configuration."""
    name: str
    description: Optional[str] = None
    keycloak_config: Optional[KeycloakConfig] = None


class ColumnMappings(BaseModel):
    """Column name mappings for query results."""
    name: Optional[str] = None
    username: Optional[str] = None
    attributes: Optional[str] = None
    roles: Optional[str] = None
    external_id: Optional[str] = None
    geometry: Optional[str] = None
    srid: Optional[int] = None


class QueryConfig(BaseModel):
    """Query configuration with optional column mappings."""
    query: str
    mappings: Optional[ColumnMappings] = None


class ConditionConfig(BaseModel):
    """ACL condition configuration."""
    op: str
    attr: Optional[str] = None
    val: Optional[Any] = None
    source: Optional[str] = None
    args: Optional[Any] = None
    conditions: Optional[List["ConditionConfig"]] = None


class ACLConfig(BaseModel):
    """ACL entry configuration for resource types or specific resources."""
    action: str
    role: Optional[str] = None
    principal: Optional[str] = None
    principal_id: Optional[int] = None
    resource_external_id: Optional[str] = None
    conditions: Optional[ConditionConfig] = None


class ResourceConfig(BaseModel):
    """Manual resource definition with optional ACLs."""
    external_id: str
    attributes: Optional[Dict[str, Any]] = None
    geometry: Optional[Union[Dict[str, Any], str, List[float]]] = None
    srid: Optional[int] = None
    acls: Optional[List[ACLConfig]] = None


class ResourceQueryConfig(BaseModel):
    """Resource query configuration."""
    query: str
    mappings: Optional[ColumnMappings] = None


class ResourceTypeConfig(BaseModel):
    """Resource type configuration."""
    name: str
    is_public: bool = False
    acls: Optional[List[ACLConfig]] = None
    resources: Optional[ResourceQueryConfig] = None
    # Manual resource definitions with ACLs
    resource_list: Optional[List[ResourceConfig]] = None


class SyncConfig(BaseModel):
    """Root configuration for the sync tool."""
    database: DatabaseConfig
    realm: RealmConfig
    actions: List[str] = Field(default_factory=list)
    roles: Optional[QueryConfig] = None
    principals: Optional[QueryConfig] = None
    resource_types: List[ResourceTypeConfig] = Field(default_factory=list)
    
    @property
    def uses_keycloak_sync(self) -> bool:
        """Check if Keycloak sync is enabled for roles/principals."""
        return (
            self.realm.keycloak_config is not None 
            and self.realm.keycloak_config.sync_groups
        )
