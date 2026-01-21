"""
Manifest generator using stateful-abac-sdk ManifestBuilder.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add SDK to path for development
SDK_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "python-sdk" / "src"
if SDK_PATH.exists():
    sys.path.insert(0, str(SDK_PATH))

from stateful_abac_sdk.manifest.builder import ManifestBuilder

from ..config.schema import (
    SyncConfig, 
    ResourceTypeConfig, 
    ResourceConfig,
    ACLConfig, 
    ConditionConfig,
    ColumnMappings
)
from ..db.connector import DatabaseConnector
import threading
import time
import itertools

class Spinner:
    def __init__(self, message="Processing", delay=0.1):
        self.spinner = itertools.cycle(['.', '..', '...'])
        self.delay = delay
        self.message = message
        self.running = False
        self.thread = None

    def spin(self):
        while self.running:
            sys.stderr.write(f"\r{self.message}{next(self.spinner)}   ")
            sys.stderr.flush()
            time.sleep(self.delay)
            # clear line
            sys.stderr.write(f"\r{' ' * (len(self.message) + 10)}")

    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stderr.write(f"\r{self.message}... Done!   \n")
        sys.stderr.flush()


def _build_condition_dict(cond: ConditionConfig) -> Dict[str, Any]:
    """Convert ConditionConfig to manifest condition dictionary."""
    result: Dict[str, Any] = {"op": cond.op}
    
    if cond.conditions:
        # Logical operator (and/or)
        result["conditions"] = [_build_condition_dict(c) for c in cond.conditions]
    else:
        # Leaf condition
        if cond.attr:
            result["attr"] = cond.attr
        if cond.val is not None:
            result["val"] = cond.val
        if cond.source:
            result["source"] = cond.source
        if cond.args is not None:
            result["args"] = cond.args
    
    return result


def _apply_mappings(row: Dict[str, Any], mappings: Optional[ColumnMappings]) -> Dict[str, Any]:
    """Apply column mappings to rename keys in query result row."""
    if not mappings:
        return row
    
    result = dict(row)
    mapping_dict = mappings.model_dump(exclude_none=True)
    
    for target_key, source_key in mapping_dict.items():
        if isinstance(source_key, str) and source_key in result:
            result[target_key] = result.pop(source_key)
    
    return result


class ManifestGenerator:
    """Generates manifests from database queries using ManifestBuilder."""
    
    def __init__(self, config: SyncConfig, db: DatabaseConnector):
        self.config = config
        self.db = db
        
    def generate(self) -> Dict[str, Any]:
        """
        Generate manifest from configured sources.
        
        Returns:
            Complete manifest dictionary.
        """
        builder = ManifestBuilder(
            self.config.realm.name,
            self.config.realm.description
        )
        
        # Configure Keycloak if present
        if self.config.realm.keycloak_config:
            kc = self.config.realm.keycloak_config
            builder.set_keycloak_config(
                server_url=kc.server_url,
                keycloak_realm=kc.keycloak_realm,
                client_id=kc.client_id,
                client_secret=kc.client_secret,
                verify_ssl=kc.verify_ssl,
                sync_cron=kc.sync_cron,
                sync_groups=kc.sync_groups,
                public_key=kc.public_key,
                algorithm=kc.algorithm,
                settings=kc.settings
            )
        
        # Add actions
        for action in self.config.actions:
            builder.add_action(action)
        
        # Fetch and add roles (unless Keycloak sync handles it)
        if self.config.roles and not self.config.uses_keycloak_sync:
            self._add_roles(builder)
        
        # Fetch and add principals (unless Keycloak sync handles it)
        if self.config.principals and not self.config.uses_keycloak_sync:
            self._add_principals(builder)
        
        # Process resource types
        total_types = len(self.config.resource_types)
        for i, rt_config in enumerate(self.config.resource_types, 1):
            print(f"[{i}/{total_types}] Processing resource type: {rt_config.name}...", file=sys.stderr)
            self._add_resource_type(builder, rt_config)
        
        return builder.build()
    
    def _add_roles(self, builder: ManifestBuilder) -> None:
        """Fetch and add roles from database."""
        roles_config = self.config.roles
        if not roles_config:
            return
            
        rows = self.db.execute_query(roles_config.query)
        
        for row in rows:
            row = _apply_mappings(row, roles_config.mappings)
            name = row.get("name")
            if name:
                attributes = row.get("attributes")
                builder.add_role(name, attributes)
    
    def _add_principals(self, builder: ManifestBuilder) -> None:
        """Fetch and add principals from database."""
        principals_config = self.config.principals
        if not principals_config:
            return
            
        rows = self.db.execute_query(principals_config.query)
        
        for row in rows:
            row = _apply_mappings(row, principals_config.mappings)
            username = row.get("username")
            if username:
                roles = row.get("roles", [])
                attributes = row.get("attributes")
                builder.add_principal(username, roles, attributes).end()
    
    def _add_resource_type(
        self, 
        builder: ManifestBuilder, 
        rt_config: ResourceTypeConfig
    ) -> None:
        """Add a resource type with its resources and ACLs."""
        # Add the resource type itself
        builder.add_resource_type(rt_config.name, rt_config.is_public)
        
        # Add type-level ACLs
        if rt_config.acls:
            for acl in rt_config.acls:
                self._add_acl(builder, rt_config.name, acl)
        
        # Fetch resources from database query
        if rt_config.resources:
            self._add_resources_from_query(builder, rt_config)
        
        # Add manually defined resources with their ACLs
        if rt_config.resource_list:
            self._add_manual_resources(builder, rt_config)
    
    def _add_acl(
        self, 
        builder: ManifestBuilder, 
        resource_type: str, 
        acl: ACLConfig,
        resource_external_id: Optional[str] = None
    ) -> None:
        """Add an ACL entry."""
        acl_builder = builder.add_acl(resource_type, acl.action)
        
        if acl.role:
            acl_builder.for_role(acl.role)
        elif acl.principal:
            acl_builder.for_principal(acl.principal)
        elif acl.principal_id is not None:
            acl_builder._data["principal_id"] = acl.principal_id
        
        # Use explicit resource_external_id from ACL, or passed from resource
        ext_id = acl.resource_external_id or resource_external_id
        if ext_id:
            acl_builder.for_resource(ext_id)
        
        if acl.conditions:
            acl_builder.when(_build_condition_dict(acl.conditions))
        
        acl_builder.end()
    
    def _add_resources_from_query(
        self, 
        builder: ManifestBuilder, 
        rt_config: ResourceTypeConfig
    ) -> None:
        """Fetch and add resources from database query."""
        resources_config = rt_config.resources
        if not resources_config:
            return
        
        with Spinner(f"  Executing query for {rt_config.name}"):
            rows = self.db.execute_query(resources_config.query)
        print(f"  Fetched {len(rows)} rows. Applying mappings...", file=sys.stderr)
        mappings = resources_config.mappings
        default_srid = mappings.srid if mappings else None
        
        for row in rows:
            row = _apply_mappings(row, mappings)
            external_id = row.get("external_id")
            
            if not external_id:
                continue
            
            res_builder = builder.add_resource(str(external_id), rt_config.name)
            
            # Add attributes
            attributes = row.get("attributes")
            if attributes and isinstance(attributes, dict):
                for key, value in attributes.items():
                    res_builder.with_attribute(key, value)
            
            # Add geometry if present
            geometry = row.get("geometry")
            if geometry:
                srid = row.get("srid", default_srid)
                res_builder.with_geometry(geometry, srid)
            
            res_builder.end()
    
    def _add_manual_resources(
        self, 
        builder: ManifestBuilder, 
        rt_config: ResourceTypeConfig
    ) -> None:
        """Add manually defined resources with their ACLs."""
        if not rt_config.resource_list:
            return
        
        for res_config in rt_config.resource_list:
            res_builder = builder.add_resource(res_config.external_id, rt_config.name)
            
            # Add attributes
            if res_config.attributes:
                for key, value in res_config.attributes.items():
                    res_builder.with_attribute(key, value)
            
            # Add geometry if present
            if res_config.geometry:
                res_builder.with_geometry(res_config.geometry, res_config.srid)
            
            res_builder.end()
            
            # Add per-resource ACLs
            if res_config.acls:
                for acl in res_config.acls:
                    self._add_acl(builder, rt_config.name, acl, res_config.external_id)
