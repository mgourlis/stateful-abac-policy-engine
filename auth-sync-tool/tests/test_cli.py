"""Tests for CLI commands."""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from stateful_abac_sync.cli import cli, validate, generate


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_config_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""
database:
  type: postgresql
  host: localhost
  port: 5432
  database: testdb
  user: testuser
  password: testpass

realm:
  name: TestRealm
  description: Test realm for CLI testing

actions:
  - view
  - edit

resource_types:
  - name: document
    is_public: false
    acls:
      - action: view
        role: reader
""")
    return config


class TestValidateCommand:
    """Tests for the validate CLI command."""
    
    def test_validate_valid_config(self, runner, valid_config_file):
        result = runner.invoke(cli, ["validate", "-c", str(valid_config_file)])
        
        assert result.exit_code == 0
        assert "Configuration is valid" in result.output
        assert "TestRealm" in result.output
    
    def test_validate_missing_file(self, runner):
        result = runner.invoke(cli, ["validate", "-c", "/nonexistent/config.yaml"])
        
        assert result.exit_code != 0
    
    def test_validate_invalid_yaml(self, runner, tmp_path):
        invalid_config = tmp_path / "invalid.yaml"
        invalid_config.write_text("not: valid: yaml:")
        
        result = runner.invoke(cli, ["validate", "-c", str(invalid_config)])
        
        assert result.exit_code != 0
        assert "Validation failed" in result.output or "Error" in result.output
    
    def test_validate_shows_realm_info(self, runner, valid_config_file):
        result = runner.invoke(cli, ["validate", "-c", str(valid_config_file)])
        
        assert "Realm: TestRealm" in result.output
        assert "Actions: 2" in result.output
        assert "Resource Types: 1" in result.output


class TestGenerateCommand:
    """Tests for the generate CLI command."""
    
    def test_generate_requires_config(self, runner):
        result = runner.invoke(cli, ["generate"])
        
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()
    
    def test_generate_missing_config_file(self, runner):
        result = runner.invoke(cli, ["generate", "-c", "/nonexistent/config.yaml"])
        
        assert result.exit_code != 0


class TestCLIHelp:
    """Tests for CLI help messages."""
    
    def test_main_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        
        assert result.exit_code == 0
        assert "Stateful ABAC Policy Engine Sync Tool" in result.output
        assert "generate" in result.output
        assert "validate" in result.output
    
    def test_generate_help(self, runner):
        result = runner.invoke(cli, ["generate", "--help"])
        
        assert result.exit_code == 0
        assert "--config" in result.output
        assert "--output" in result.output
        assert "--stdout" in result.output
    
    def test_validate_help(self, runner):
        result = runner.invoke(cli, ["validate", "--help"])
        
        assert result.exit_code == 0
        assert "--config" in result.output
    
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        
        assert result.exit_code == 0
        assert "0.1.0" in result.output
