"""
Configuration loader for YAML files.
"""

from pathlib import Path
from typing import Union
import yaml

from .schema import SyncConfig


def load_config(config_path: Union[str, Path]) -> SyncConfig:
    """
    Load and validate configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file.
        
    Returns:
        Validated SyncConfig object.
        
    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If YAML parsing fails.
        pydantic.ValidationError: If config validation fails.
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)
    
    return SyncConfig(**raw_config)
