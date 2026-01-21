"""Tests for configuration schema and loader."""

import os
import pytest
from pathlib import Path

from stateful_abac_sync.config.schema import (
    SyncConfig, DatabaseConfig, RealmConfig, KeycloakConfig,
    ResourceTypeConfig, ACLConfig, QueryConfig, expand_env_vars
)
from stateful_abac_sync.config.loader import load_config


class TestExpandEnvVars:
    """Tests for environment variable expansion."""
    
    def test_expand_single_var(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "secret_value")
        result = expand_env_vars("password=${TEST_VAR}")
        assert result == "password=secret_value"
    
    def test_expand_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "5432")
        result = expand_env_vars("${HOST}:${PORT}")
        assert result == "localhost:5432"
    
    def test_missing_var_unchanged(self):
        result = expand_env_vars("${UNDEFINED_VAR}")
        assert result == "${UNDEFINED_VAR}"
    
    def test_no_vars_unchanged(self):
        result = expand_env_vars("plain text")
        assert result == "plain text"


class TestDatabaseConfig:
    """Tests for DatabaseConfig model."""
    
    def test_defaults(self):
        config = DatabaseConfig(database="testdb", user="testuser")
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.type == "postgresql"
    
    def test_password_env_expansion(self, monkeypatch):
        monkeypatch.setenv("DB_PASS", "secret123")
        config = DatabaseConfig(
            database="testdb",
            user="testuser",
            password="${DB_PASS}"
        )
        assert config.password == "secret123"


class TestKeycloakConfig:
    """Tests for KeycloakConfig model."""
    
    def test_defaults(self):
        config = KeycloakConfig(
            server_url="https://sso.example.com",
            keycloak_realm="myrealm",
            client_id="myclient"
        )
        assert config.verify_ssl is True
        assert config.sync_groups is False
        assert config.algorithm == "RS256"
    
    def test_secret_env_expansion(self, monkeypatch):
        monkeypatch.setenv("KC_SECRET", "client_secret_value")
        config = KeycloakConfig(
            server_url="https://sso.example.com",
            keycloak_realm="myrealm",
            client_id="myclient",
            client_secret="${KC_SECRET}"
        )
        assert config.client_secret == "client_secret_value"


class TestRealmConfig:
    """Tests for RealmConfig model."""
    
    def test_basic(self):
        config = RealmConfig(name="TestRealm")
        assert config.name == "TestRealm"
        assert config.description is None
        assert config.keycloak_config is None
    
    def test_with_keycloak(self):
        config = RealmConfig(
            name="TestRealm",
            keycloak_config={
                "server_url": "https://sso.example.com",
                "keycloak_realm": "myrealm",
                "client_id": "myclient"
            }
        )
        assert config.keycloak_config is not None
        assert config.keycloak_config.server_url == "https://sso.example.com"


class TestResourceTypeConfig:
    """Tests for ResourceTypeConfig model."""
    
    def test_defaults(self):
        config = ResourceTypeConfig(name="document")
        assert config.name == "document"
        assert config.is_public is False
        assert config.acls is None
        assert config.resources is None
    
    def test_with_acls(self):
        config = ResourceTypeConfig(
            name="document",
            is_public=False,
            acls=[
                {"action": "view", "role": "reader"},
                {"action": "edit", "role": "editor"}
            ]
        )
        assert len(config.acls) == 2
        assert config.acls[0].action == "view"
        assert config.acls[0].role == "reader"


class TestSyncConfig:
    """Tests for the root SyncConfig model."""
    
    def test_minimal_config(self):
        config = SyncConfig(
            database={"database": "testdb", "user": "testuser"},
            realm={"name": "TestRealm"}
        )
        assert config.realm.name == "TestRealm"
        assert config.actions == []
        assert config.resource_types == []
    
    def test_uses_keycloak_sync_false_by_default(self):
        config = SyncConfig(
            database={"database": "testdb", "user": "testuser"},
            realm={"name": "TestRealm"}
        )
        assert config.uses_keycloak_sync is False
    
    def test_uses_keycloak_sync_true(self):
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
            }
        )
        assert config.uses_keycloak_sync is True
    
    def test_full_config(self):
        config = SyncConfig(
            database={"database": "testdb", "user": "testuser"},
            realm={"name": "TestRealm", "description": "Test"},
            actions=["view", "edit", "delete"],
            roles={"query": "SELECT * FROM roles"},
            principals={"query": "SELECT * FROM users"},
            resource_types=[
                {"name": "document", "is_public": False},
                {"name": "public_notice", "is_public": True}
            ]
        )
        assert len(config.actions) == 3
        assert config.roles.query == "SELECT * FROM roles"
        assert len(config.resource_types) == 2


class TestLoadConfig:
    """Tests for YAML config loading."""
    
    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
database:
  type: postgresql
  host: localhost
  port: 5432
  database: testdb
  user: testuser
  password: testpass

realm:
  name: TestRealm

actions:
  - view
  - edit

resource_types:
  - name: document
    is_public: false
""")
        config = load_config(config_file)
        assert config.realm.name == "TestRealm"
        assert len(config.actions) == 2
        assert len(config.resource_types) == 1
    
    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")
    
    def test_load_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("invalid: yaml: content:")
        
        with pytest.raises(Exception):  # yaml.YAMLError or pydantic.ValidationError
            load_config(config_file)
