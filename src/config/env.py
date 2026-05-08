"""
Environment configuration using python-dotenv.
"""

import os
from typing import Optional
from dotenv import load_dotenv


def load_env() -> dict:
    """
    Load environment variables from .env file.
    
    Returns:
        Dictionary of loaded environment variables
    """
    # Load from .env file
    load_dotenv()
    
    # Define default configuration
    defaults = {
        # Instagram
        'INSTAGRAM_SESSION_ID': '',
        
        # Visual AI
        'VISUAL_AI_TYPE': 'ollama',  # ollama or llama.cpp
        'VISUAL_AI_OLLAMA_HOST': 'http://localhost:11434',
        'VISUAL_AI_OLLAMA_MODEL': 'llava',
        'VISUAL_AI_LLAMA_HOST': 'http://localhost:8080',
        'VISUAL_AI_LLAMA_MODEL': 'gemma4',
        
        # Processing
        'OUTPUT_DIR': './dataset',
        'MAX_IMAGES': '1000',
        'RATE_LIMIT_DELAY': '1',
        'IMAGE_QUALITY': '90',
        'TARGET_SIZE_MB': '5',
        
        # Captioning
        'GENERATE_CAPTIONS': 'false',
        'CAPTION_PAIRS_FORMAT': 'text_image',
        
        # Filtering
        'FILTERING_ENABLED': 'false',
        'MIN_CONFIDENCE': '0.7',
        'FILTERING_PROMPT': '',
        
        # Test configuration
        'TEST_USERNAME': '',
        'TEST_SESSION_ID': '',
        'TEST_EXAMPLE_IMAGES': '',
    }
    
    # Load environment variables with defaults
    env = {}
    for key, default_value in defaults.items():
        value = os.getenv(key)
        if value is None:
            env[key] = default_value
        else:
            env[key] = value
    
    return env


def get_int(key: str, default: int) -> int:
    """Get integer value from environment."""
    try:
        return int(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def get_float(key: str, default: float) -> float:
    """Get float value from environment."""
    try:
        return float(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def get_bool(key: str, default: bool) -> bool:
    """Get boolean value from environment."""
    value = os.getenv(key, str(default).lower())
    return value.lower() in ('true', '1', 'yes', 'on')


def get_str(key: str, default: str) -> str:
    """Get string value from environment."""
    return os.getenv(key, default)


class EnvConfig:
    """Central configuration manager from environment variables."""
    
    def __init__(self):
        self._env = load_env()
    
    @property
    def instagram_session_id(self) -> str:
        """Instagram session ID for authentication."""
        return self._env.get('INSTAGRAM_SESSION_ID', '')
    
    @property
    def test_session_id(self) -> str:
        """Test session ID."""
        return self._env.get('TEST_SESSION_ID', '')
    
    @property
    def test_username(self) -> str:
        """Test username."""
        return self._env.get('TEST_USERNAME', '')
    
    @property
    def test_example_images(self) -> str:
        """Test example images directory."""
        return self._env.get('TEST_EXAMPLE_IMAGES', '')
    
    @property
    def visual_ai_type(self) -> str:
        """Visual AI type: ollama or llama.cpp"""
        return self._env.get('VISUAL_AI_TYPE', 'ollama')
    
    @property
    def visual_ai_ollama_host(self) -> str:
        """Ollama API host."""
        return self._env.get('VISUAL_AI_OLLAMA_HOST', 'http://localhost:11434')
    
    @property
    def visual_ai_ollama_model(self) -> str:
        """Ollama model name."""
        return self._env.get('VISUAL_AI_OLLAMA_MODEL', 'llava')
    
    @property
    def visual_ai_llama_host(self) -> str:
        """llama.cpp API host."""
        return self._env.get('VISUAL_AI_LLAMA_HOST', 'http://localhost:8080')
    
    @property
    def visual_ai_llama_model(self) -> str:
        """llama.cpp model name."""
        return self._env.get('VISUAL_AI_LLAMA_MODEL', 'gemma4')
    
    @property
    def output_dir(self) -> str:
        """Output directory for downloaded images."""
        return self._env.get('OUTPUT_DIR', './dataset')
    
    @property
    def max_images(self) -> int:
        """Maximum number of images to download."""
        return get_int('MAX_IMAGES', 1000)
    
    @property
    def rate_limit_delay(self) -> int:
        """Delay between requests in seconds."""
        return get_int('RATE_LIMIT_DELAY', 1)
    
    @property
    def image_quality(self) -> int:
        """Image quality for saving (0-100)."""
        return get_int('IMAGE_QUALITY', 90)
    
    @property
    def target_size_mb(self) -> float:
        """Target maximum file size in MB."""
        return get_float('TARGET_SIZE_MB', 5.0)
    
    @property
    def generate_captions(self) -> bool:
        """Whether to generate captions with Visual AI."""
        return get_bool('GENERATE_CAPTIONS', False)
    
    @property
    def caption_pairs_format(self) -> str:
        """Format for caption pairs output."""
        return self._env.get('CAPTION_PAIRS_FORMAT', 'text_image')
    
    @property
    def filtering_enabled(self) -> bool:
        """Whether to enable image filtering."""
        return get_bool('FILTERING_ENABLED', False)
    
    @property
    def min_confidence(self) -> float:
        """Minimum confidence threshold for filtering."""
        return get_float('MIN_CONFIDENCE', 0.7)
    
    @property
    def filtering_prompt(self) -> str:
        """Prompt used for filtering images."""
        return self._env.get('FILTERING_PROMPT', '')
    
    def validate(self) -> list:
        """
        Validate configuration.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if not self.instagram_session_id:
            errors.append("INSTAGRAM_SESSION_ID is not set")
        
        if self.visual_ai_type not in ['ollama', 'llama.cpp']:
            errors.append(f"Invalid VISUAL_AI_TYPE: {self.visual_ai_type}")  
        
        if not self.output_dir:
            errors.append("OUTPUT_DIR is not set")
        
        return errors
