"""Tests for manifest generator."""

import pytest
from unittest.mock import MagicMock

from stateful_abac_sync.config.schema import (
    SyncConfig, ResourceTypeConfig, ACLConfig, ConditionConfig,
    QueryConfig, ResourceQueryConfig, ColumnMappings
)
from stateful_abac_sync.generator.manifest import (
    ManifestGenerator, _build_condition_dict, _apply_mappings
)


class MockDB:
    """Mock database connector for testing."""
    
    def __init__(self, query_results=None):
        self.query_results = query_results or {}
        self.executed_queries = []
    
    def execute_query(self, query: str):
        self.executed_queries.append(query)
        return self.query_results.get(query, [])


class TestBuildConditionDict:
    """Tests for condition dictionary building."""
    
    def test_simple_equality(self):
        cond = ConditionConfig(op="=", attr="status", val="active", source="resource")
        result = _build_condition_dict(cond)
        
        assert result["op"] == "="
        assert result["attr"] == "status"
        assert result["val"] == "active"
        assert result["source"] == "resource"
    
    def test_spatial_condition(self):
        cond = ConditionConfig(
            op="st_dwithin",
            attr="geometry",
            val="$context.location",
            args=1000
        )
        result = _build_condition_dict(cond)
        
        assert result["op"] == "st_dwithin"
        assert result["args"] == 1000
    
    def test_nested_and_condition(self):
        cond = ConditionConfig(
            op="and",
            conditions=[
                ConditionConfig(op="=", attr="status", val="active"),
                ConditionConfig(op=">=", attr="level", val=5)
            ]
        )
        result = _build_condition_dict(cond)
        
        assert result["op"] == "and"
        assert len(result["conditions"]) == 2
        assert result["conditions"][0]["attr"] == "status"
        assert result["conditions"][1]["attr"] == "level"


class TestApplyMappings:
    """Tests for column mapping application."""
    
    def test_no_mappings(self):
        row = {"col1": "val1", "col2": "val2"}
        result = _apply_mappings(row, None)
        assert result == row
    
    def test_simple_mapping(self):
        row = {"user_name": "alice", "user_email": "alice@example.com"}
        mappings = ColumnMappings(username="user_name")
        result = _apply_mappings(row, mappings)
        
        assert result["username"] == "alice"
        assert "user_name" not in result
        assert "user_email" in result
    
    def test_mapping_preserves_unmapped(self):
        row = {"name": "test", "extra": "data"}
        mappings = ColumnMappings(name="name")
        result = _apply_mappings(row, mappings)
        
        assert "extra" in result


class TestManifestGenerator:
    """Tests for ManifestGenerator class."""
    
    @pytest.fixture
    def minimal_config(self):
        return SyncConfig(
            database={"database": "testdb", "user": "testuser"},
            realm={"name": "TestRealm", "description": "Test realm"}
        )
    
    def test_generate_minimal(self, minimal_config):
        """Test generating manifest with minimal config."""
        db = MockDB()
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert manifest["realm"]["name"] == "TestRealm"
        assert manifest["realm"]["description"] == "Test realm"
    
    def test_generate_with_actions(self, minimal_config):
        """Test actions are included in manifest."""
        minimal_config.actions = ["view", "edit", "delete"]
        
        db = MockDB()
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert manifest["actions"] == ["view", "edit", "delete"]
    
    def test_generate_with_resource_types(self, minimal_config):
        """Test resource types are included in manifest."""
        minimal_config.resource_types = [
            ResourceTypeConfig(name="document", is_public=False),
            ResourceTypeConfig(name="announcement", is_public=True)
        ]
        
        db = MockDB()
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert len(manifest["resource_types"]) == 2
        assert manifest["resource_types"][0]["name"] == "document"
        assert manifest["resource_types"][0]["is_public"] is False
        assert manifest["resource_types"][1]["is_public"] is True
    
    def test_generate_with_type_acls(self, minimal_config):
        """Test ACLs are included for resource types."""
        minimal_config.resource_types = [
            ResourceTypeConfig(
                name="document",
                acls=[
                    ACLConfig(action="view", role="reader"),
                    ACLConfig(action="edit", role="editor")
                ]
            )
        ]
        
        db = MockDB()
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert len(manifest["acls"]) == 2
        assert manifest["acls"][0]["resource_type"] == "document"
        assert manifest["acls"][0]["action"] == "view"
        assert manifest["acls"][0]["role"] == "reader"
    
    def test_generate_with_conditional_acl(self, minimal_config):
        """Test ACLs with conditions are properly generated."""
        minimal_config.resource_types = [
            ResourceTypeConfig(
                name="facility",
                acls=[
                    ACLConfig(
                        action="enter",
                        role="agent",
                        conditions=ConditionConfig(
                            op="=",
                            attr="status",
                            val="active",
                            source="resource"
                        )
                    )
                ]
            )
        ]
        
        db = MockDB()
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert "conditions" in manifest["acls"][0]
        assert manifest["acls"][0]["conditions"]["op"] == "="
        assert manifest["acls"][0]["conditions"]["attr"] == "status"
    
    def test_generate_with_roles_query(self, minimal_config):
        """Test roles are fetched from database."""
        minimal_config.roles = QueryConfig(query="SELECT name FROM roles")
        
        db = MockDB({
            "SELECT name FROM roles": [
                {"name": "admin"},
                {"name": "editor"},
                {"name": "viewer"}
            ]
        })
        
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert len(manifest["roles"]) == 3
        assert manifest["roles"][0]["name"] == "admin"
    
    def test_generate_with_principals_query(self, minimal_config):
        """Test principals are fetched from database."""
        minimal_config.principals = QueryConfig(query="SELECT username, roles FROM users")
        
        db = MockDB({
            "SELECT username, roles FROM users": [
                {"username": "alice", "roles": ["admin"]},
                {"username": "bob", "roles": ["editor", "viewer"]}
            ]
        })
        
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert len(manifest["principals"]) == 2
        assert manifest["principals"][0]["username"] == "alice"
        assert manifest["principals"][0]["roles"] == ["admin"]
    
    def test_generate_with_resources_query(self, minimal_config):
        """Test resources are fetched from database."""
        minimal_config.resource_types = [
            ResourceTypeConfig(
                name="document",
                resources=ResourceQueryConfig(
                    query="SELECT id as external_id, attrs as attributes FROM docs"
                )
            )
        ]
        
        db = MockDB({
            "SELECT id as external_id, attrs as attributes FROM docs": [
                {"external_id": "DOC-001", "attributes": {"title": "Test Doc"}},
                {"external_id": "DOC-002", "attributes": {"title": "Another Doc"}}
            ]
        })
        
        generator = ManifestGenerator(minimal_config, db)
        manifest = generator.generate()
        
        assert len(manifest["resources"]) == 2
        assert manifest["resources"][0]["external_id"] == "DOC-001"
        assert manifest["resources"][0]["type"] == "document"
    
    def test_keycloak_sync_skips_roles_principals(self):
        """Test that roles/principals queries are skipped when Keycloak sync is enabled."""
        config = SyncConfig(
            database={"database": "testdb", "user": "testuser"},
            realm={
                "name": "TestRealm",
                "keycloak_config": {
                    "server_url": "https://sso.example.com",
                    "keycloak_realm": "myrealm",
                    "client_id": "myclient",
                    "sync_groups": True
                }
            },
            roles=QueryConfig(query="SELECT name FROM roles"),
            principals=QueryConfig(query="SELECT username FROM users")
        )
        
        db = MockDB()
        generator = ManifestGenerator(config, db)
        manifest = generator.generate()
        
        # Queries should not have been executed
        assert len(db.executed_queries) == 0
        assert "roles" not in manifest
        assert "principals" not in manifest
    
    def test_keycloak_config_in_manifest(self):
        """Test Keycloak config is included in manifest."""
        config = SyncConfig(
            database={"database": "testdb", "user": "testuser"},
            realm={
                "name": "TestRealm",
                "keycloak_config": {
                    "server_url": "https://sso.example.com",
                    "keycloak_realm": "myrealm",
                    "client_id": "myclient",
                    "sync_groups": True,
                    "public_key": "-----BEGIN PUBLIC KEY-----",
                    "algorithm": "RS256"
                }
            }
        )
        
        db = MockDB()
        generator = ManifestGenerator(config, db)
        manifest = generator.generate()
        
        kc = manifest["realm"]["keycloak_config"]
        assert kc["server_url"] == "https://sso.example.com"
        assert kc["sync_groups"] is True
        assert kc["public_key"] == "-----BEGIN PUBLIC KEY-----"
        assert kc["algorithm"] == "RS256"
