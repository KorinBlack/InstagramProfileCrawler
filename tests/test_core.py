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
from src.images.deduplicator import ImageDeduplicator
from src.images.optimizer import ImageOptimizer


@pytest.fixture
def clean_env(monkeypatch):
    """Ignore the local .env file and any VISUAL_AI_* / OUTPUT_* variables."""
    import src.config.env as env_module
    monkeypatch.setattr(env_module, "load_dotenv", lambda *a, **k: None)
    for key in list(os.environ):
        if key.startswith(("VISUAL_AI_", "OUTPUT_DIR", "MAX_IMAGES", "INSTAGRAM_")):
            monkeypatch.delenv(key, raising=False)


class TestEnvConfig:
    """Test environment configuration."""

    def test_load_env(self, clean_env):
        """Test that environment variables are loaded."""
        config = EnvConfig()

        assert hasattr(config, 'instagram_session_id')
        assert hasattr(config, 'visual_ai_type')
        assert hasattr(config, 'output_dir')

    def test_default_values(self, clean_env):
        """Test default configuration values."""
        config = EnvConfig()

        assert config.visual_ai_type == 'ollama'
        assert config.visual_ai_ollama_host == 'http://localhost:11434'
        assert config.output_dir == './dataset'
        assert config.max_images == 1000

    def test_strata_endpoint(self, clean_env, monkeypatch):
        """Strata is a valid engine and resolves its own host/model."""
        monkeypatch.setenv("VISUAL_AI_TYPE", "strata")
        config = EnvConfig()

        engine, host, model = config.visual_ai_endpoint()
        assert engine == 'strata'
        assert host == 'http://127.0.0.1:8080'
        assert model == 'qwen3.8-flash-next'
        assert not any('VISUAL_AI_TYPE' in e for e in config.validate())

    def test_endpoint_override(self, clean_env):
        """An explicit engine overrides VISUAL_AI_TYPE."""
        engine, host, _ = EnvConfig().visual_ai_endpoint("llama.cpp")
        assert engine == 'llama.cpp'
        assert host == 'http://localhost:8080'


class TestVisualAI:
    """Test Visual AI engine selection and response handling (no network)."""

    @staticmethod
    def _image(tmp_path):
        from PIL import Image
        path = tmp_path / "img.png"
        Image.new('RGBA', (64, 64), color='red').save(path)
        return str(path)

    def test_engine_selection(self):
        from src.filtering.visual_ai import VisualAI
        ai = VisualAI(host="http://127.0.0.1:8080/v1/", model="m", engine="strata")
        assert ai.engine == "strata"
        assert not ai.use_ollama
        assert ai.host == "http://127.0.0.1:8080"
        # Backward compatibility with use_ollama=False
        assert VisualAI(host="http://x", use_ollama=False).engine == "llama.cpp"
        with pytest.raises(ValueError):
            VisualAI(engine="unknown")

    def test_filter_parses_json_and_strips_thinking(self, tmp_path, monkeypatch):
        from src.filtering.visual_ai import VisualAI
        ai = VisualAI(host="http://127.0.0.1:8080", model="m", engine="strata")
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content":
                    '<think>{"keep": true}</think>\n{"keep": false, "reason": "blurry", "confidence": 0.9}'}}]}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            return FakeResponse()

        monkeypatch.setattr("src.filtering.visual_ai.requests.post", fake_post)
        result = ai.filter_image(self._image(tmp_path), "only portraits")

        assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
        assert result.success
        assert result.filtered is True
        assert result.confidence == 0.9

    def test_filter_ollama_path(self, tmp_path):
        """Regression: the Ollama path used to leave response_text unset."""
        from src.filtering.visual_ai import VisualAI
        ai = VisualAI(engine="ollama")
        ai.available = True

        class FakeClient:
            def generate(self, **kwargs):
                return {"response": '{"keep": true, "confidence": 0.8}'}

        ai.client = FakeClient()
        result = ai.filter_image(self._image(tmp_path), "")
        assert result.success
        assert result.filtered is False

    def test_caption_generator_processes_all_images(self, tmp_path):
        from src.filtering.visual_ai import CaptionGenerator
        seen = []

        class FakeAI:
            def generate_caption_pairs(self, path, out):
                seen.append(path)
                yield {"image": path}

        results = CaptionGenerator(FakeAI(), batch_size=2).generate_all(["a", "b", "c"], str(tmp_path))
        assert seen == ["a", "b", "c"]
        assert len(results) == 3


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

    def test_remove_duplicates(self, tmp_path):
        """Duplicates are deleted, one copy of each group is kept."""
        from PIL import Image
        import shutil
        Image.new('RGB', (32, 32), color='red').save(tmp_path / "a.jpg")
        shutil.copy(tmp_path / "a.jpg", tmp_path / "b.jpg")
        Image.new('RGB', (32, 32), color='blue').save(tmp_path / "c.jpg")

        removed = ImageDeduplicator().remove_duplicates(str(tmp_path))

        assert len(removed) == 1
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg", "c.jpg"]


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
        assert Path(result.path).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
