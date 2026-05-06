"""
Test module for InstagramProfileCrawler.
"""

import pytest
from pathlib import Path
import sys
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import from absolute paths
from src.config.env import EnvConfig
from src.utils.logger import Logger
from src.utils.stats import StatisticsTracker


class TestEnvConfig:
    """Test environment configuration."""
    
    def test_load_env(self):
        """Test that environment variables are loaded."""
        config = EnvConfig()
        
        # Should have default values
        assert hasattr(config, 'instagram_session_id')
        assert hasattr(config, 'visual_ai_route')
        assert hasattr(config, 'output_dir')
    
    def test_default_values(self):
        """Test default configuration values."""
        config = EnvConfig()
        
        # Check some defaults
        assert config.visual_ai_route == 'http://localhost:11434/api/generate'
        assert config.output_dir == './dataset'
        assert config.max_images == 1000


class TestLogger:
    """Test logging functionality."""
    
    def test_logger_creation(self):
        """Test logger can be created."""
        logger = Logger("TestApp")
        assert logger.name == "TestApp"
    
    def test_print_header(self, capsys):
        """Test header printing."""
        logger = Logger("TestApp")
        logger.print_header("Test Header", "Test Subtitle")
        
        captured = capsys.readouterr()
        assert "Test Header" in captured.out


class TestStatisticsTracker:
    """Test statistics tracking."""
    
    def test_basic_tracking(self):
        """Test basic statistics tracking."""
        stats = StatisticsTracker()
        
        # Record some activity
        stats.record_download(True, 1024, 100)
        stats.record_processing(True, optimized=True)
        stats.record_caption(True, tokens=100)
        stats.record_image(1, 1)
        
        summary = stats.get_summary()
        
        assert "Downloads" in summary
        assert "Processing" in summary
        assert "Captions" in summary


class TestImageDeduplicator:
    """Test image deduplication."""
    
    def test_deduplicator_creation(self):
        """Test deduplicator can be created."""
        deduplicator = ImageDeduplicator()
        assert deduplicator.hash_size == 16
    
    def test_compute_hash(self, tmp_path):
        """Test hash computation on real image."""
        deduplicator = ImageDeduplicator()
        
        # Create a test image
        test_image = tmp_path / "test.jpg"
        from PIL import Image
        Image.new('RGB', (100, 100), color='red').save(test_image)
        
        # Compute hash
        hash_value = deduplicator.compute_hash(str(test_image))
        
        assert hash_value
        assert len(hash_value) == 16


class TestImageOptimizer:
    """Test image optimization."""
    
    def test_optimizer_creation(self):
        """Test optimizer can be created."""
        optimizer = ImageOptimizer(target_size=1024)
        assert optimizer.target_size == 1024
    
    def test_optimize_image(self, tmp_path):
        """Test image optimization."""
        optimizer = ImageOptimizer(target_size=512)
        
        # Create a test image
        test_image = tmp_path / "test.jpg"
        from PIL import Image
        Image.new('RGB', (1024, 1024), color='blue').save(test_image)
        
        # Optimize
        result = optimizer.optimize_image(str(test_image), str(tmp_path))
        
        assert result.success
        assert result.path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
