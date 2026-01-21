"""
CLI entry point for the Stateful ABAC Policy Engine Sync Tool.
"""

import json
import sys
from pathlib import Path

import click

from .config.loader import load_config
from .db.connector import DatabaseConnector
from .generator.manifest import ManifestGenerator


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Stateful ABAC Policy Engine Sync Tool - Generate manifests from external databases."""
    pass


@cli.command()
@click.option(
    "-c", "--config",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to YAML configuration file"
)
@click.option(
    "-o", "--output",
    default="manifest.json",
    type=click.Path(path_type=Path),
    help="Output manifest file path"
)
@click.option(
    "--stdout",
    is_flag=True,
    help="Print manifest to stdout instead of file"
)
@click.option(
    "--indent",
    default=2,
    type=int,
    help="JSON indentation level"
)
def generate(config: Path, output: Path, stdout: bool, indent: int):
    """Generate a manifest.json from database sources."""
    
    try:
        # Load configuration
        click.echo(f"Loading configuration from {config}...", err=True)
        sync_config = load_config(config)
        
        # Connect to database
        db = DatabaseConnector()
        try:
            click.echo("Connecting to database...", err=True)
            db.connect(sync_config.database)
            
            # Generate manifest 
            click.echo("Generating manifest...", err=True)
            generator = ManifestGenerator(sync_config, db)
            manifest = generator.generate()
        finally:
            db.close()
        
        # Output manifest
        json_output = json.dumps(manifest, indent=indent, ensure_ascii=False)
        
        if stdout:
            click.echo(json_output)
        else:
            with open(output, 'w') as f:
                f.write(json_output)
            click.echo(f"Manifest written to {output}", err=True)
            
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "-c", "--config",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to YAML configuration file"
)
def validate(config: Path):
    """Validate a configuration file without connecting to database."""
    
    try:
        click.echo(f"Validating {config}...")
        sync_config = load_config(config)
        
        click.echo(click.style("✓ Configuration is valid!", fg="green"))
        click.echo(f"  Realm: {sync_config.realm.name}")
        click.echo(f"  Actions: {len(sync_config.actions)}")
        click.echo(f"  Resource Types: {len(sync_config.resource_types)}")
        
        if sync_config.realm.keycloak_config:
            click.echo(f"  Keycloak: {sync_config.realm.keycloak_config.server_url}")
        
        if sync_config.roles:
            click.echo("  Roles: query configured")
        
        if sync_config.principals:
            click.echo("  Principals: query configured")
            
    except FileNotFoundError as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Validation failed: {e}", fg="red"), err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
