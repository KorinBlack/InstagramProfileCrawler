"""
YAML configuration file support.
"""

from typing import Dict, Any
from pathlib import Path
import yaml


def load_yaml_config(config_path: str = "config/settings.yaml") -> Dict[str, Any]:
    """
    Load YAML configuration file.
    
    Args:
        config_path: Path to YAML file
        
    Returns:
        Dictionary of configuration values
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        print(f"⚠ Failed to load YAML config: {e}")
        return {}


def merge_configs(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two configuration dictionaries.
    
    Args:
        default: Default configuration
        override: Override configuration
        
    Returns:
        Merged configuration
    """
    result = default.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


class YAMLConfig:
    """YAML configuration manager."""
    
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self.config = load_yaml_config(config_path)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def validate(self) -> list:
        """Validate configuration."""
        errors = []
        
        # Required sections
        required_sections = ['profile', 'output']
        
        for section in required_sections:
            if section not in self.config:
                errors.append(f"Missing required section: {section}")
        
        # Validate profile section
        if 'profile' in self.config:
            profile = self.config['profile']
            if 'username' not in profile:
                errors.append("profile.username is required")
        
        # Validate output section
        if 'output' in self.config:
            output = self.config['output']
            if 'format' not in output:
                errors.append("output.format is required")
        
        return errors
