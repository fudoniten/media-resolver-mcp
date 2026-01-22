"""Unit tests for configuration management."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from media_resolver.config import (
    Config,
    LLMBackend,
    LLMConfig,
    MopidyConfig,
    IcecastConfig,
    ServerConfig,
    PodcastFeed,
    GenreMapping,
    Settings,
    load_config,
    get_config,
    set_config,
    reload_config,
)


class TestLLMBackend:
    """Tests for LLMBackend model."""

    def test_create_backend(self):
        """Test creating an LLM backend configuration."""
        backend = LLMBackend(
            name="test-backend",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            max_tokens=2000,
        )
        assert backend.name == "test-backend"
        assert backend.provider == "anthropic"
        assert backend.model == "claude-3-5-sonnet-20241022"
        assert backend.temperature == 0.7
        assert backend.max_tokens == 2000

    def test_backend_with_optional_fields(self):
        """Test backend with optional base_url and api_key."""
        backend = LLMBackend(
            name="ollama",
            provider="ollama",
            model="llama2",
            base_url="http://localhost:11434",
            api_key="test-key",
        )
        assert backend.base_url == "http://localhost:11434"
        assert backend.api_key == "test-key"

    def test_temperature_validation(self):
        """Test temperature bounds validation."""
        with pytest.raises(ValueError):
            LLMBackend(
                name="test",
                provider="anthropic",
                model="claude",
                temperature=3.0,  # Too high
            )

        with pytest.raises(ValueError):
            LLMBackend(
                name="test",
                provider="anthropic",
                model="claude",
                temperature=-0.1,  # Too low
            )


class TestLLMConfig:
    """Tests for LLMConfig model."""

    def test_get_active_backend(self):
        """Test retrieving the active backend."""
        backend1 = LLMBackend(name="backend1", provider="anthropic", model="claude")
        backend2 = LLMBackend(name="backend2", provider="openai", model="gpt-4")

        config = LLMConfig(backends=[backend1, backend2], active_backend="backend2")

        active = config.get_active_backend()
        assert active is not None
        assert active.name == "backend2"
        assert active.provider == "openai"

    def test_get_active_backend_fallback(self):
        """Test fallback to first backend if active not found."""
        backend1 = LLMBackend(name="backend1", provider="anthropic", model="claude")
        backend2 = LLMBackend(name="backend2", provider="openai", model="gpt-4")

        config = LLMConfig(backends=[backend1, backend2], active_backend="nonexistent")

        active = config.get_active_backend()
        assert active is not None
        assert active.name == "backend1"

    def test_get_active_backend_empty(self):
        """Test get_active_backend with no backends."""
        config = LLMConfig(backends=[], active_backend="default")
        active = config.get_active_backend()
        assert active is None

    def test_legacy_to_new_format_conversion(self):
        """Test automatic conversion of legacy single backend config."""
        config = LLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            temperature=0.8,
            max_tokens=1500,
        )

        # Should auto-convert to new format
        assert len(config.backends) == 1
        backend = config.backends[0]
        assert backend.name == "default"
        assert backend.provider == "anthropic"
        assert backend.model == "claude-3-5-sonnet-20241022"
        assert backend.temperature == 0.8
        assert backend.max_tokens == 1500
        assert config.active_backend == "default"


class TestMopidyConfig:
    """Tests for MopidyConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MopidyConfig()
        assert config.rpc_url == "http://localhost:6680/mopidy/rpc"
        assert config.timeout == 10

    def test_custom_values(self):
        """Test custom configuration."""
        config = MopidyConfig(
            rpc_url="http://mopidy:6680/mopidy/rpc",
            timeout=30,
        )
        assert config.rpc_url == "http://mopidy:6680/mopidy/rpc"
        assert config.timeout == 30


class TestIcecastConfig:
    """Tests for IcecastConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = IcecastConfig()
        assert config.stream_url == "http://localhost:8000/mopidy"
        assert config.mount == "/mopidy"


class TestPodcastFeed:
    """Tests for PodcastFeed model."""

    def test_create_feed(self):
        """Test creating a podcast feed configuration."""
        feed = PodcastFeed(
            name="Test Podcast",
            rss_url="https://example.com/feed.xml",
            tags=["technology", "news"],
        )
        assert feed.name == "Test Podcast"
        assert feed.rss_url == "https://example.com/feed.xml"
        assert feed.tags == ["technology", "news"]

    def test_empty_tags(self):
        """Test feed with no tags."""
        feed = PodcastFeed(name="Test", rss_url="https://example.com/feed.xml")
        assert feed.tags == []


class TestGenreMapping:
    """Tests for GenreMapping model."""

    def test_create_mapping(self):
        """Test creating a genre mapping."""
        mapping = GenreMapping(
            genre="jazz",
            playlists=["Jazz Classics", "Smooth Jazz"],
            podcast_shows=["Jazz History Podcast"],
        )
        assert mapping.genre == "jazz"
        assert len(mapping.playlists) == 2
        assert len(mapping.podcast_shows) == 1


class TestConfig:
    """Tests for main Config model."""

    def test_default_config(self):
        """Test creating config with all defaults."""
        config = Config()
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 8000
        assert config.mopidy.timeout == 10
        assert config.max_request_history == 500

    def test_full_config(self):
        """Test creating a fully populated config."""
        config = Config(
            server=ServerConfig(host="127.0.0.1", port=9000, log_level="DEBUG"),
            mopidy=MopidyConfig(
                rpc_url="http://custom:6680/mopidy/rpc",
                timeout=20,
            ),
            podcast_feeds=[
                PodcastFeed(name="Show1", rss_url="https://example.com/feed1.xml", tags=["tech"])
            ],
            genre_mappings=[GenreMapping(genre="rock", playlists=["Rock Hits"])],
            max_request_history=1000,
        )

        assert config.server.host == "127.0.0.1"
        assert config.server.port == 9000
        assert len(config.podcast_feeds) == 1
        assert len(config.genre_mappings) == 1


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_from_yaml(self):
        """Test loading configuration from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "server": {"host": "0.0.0.0", "port": 8000, "log_level": "INFO"},
                "mopidy": {"rpc_url": "http://mopidy:6680/mopidy/rpc", "timeout": 10},
                "icecast": {"stream_url": "http://icecast:8000/mopidy", "mount": "/mopidy"},
                "llm": {
                    "backends": [
                        {
                            "name": "claude",
                            "provider": "anthropic",
                            "model": "claude-3-5-sonnet-20241022",
                            "temperature": 0.7,
                            "max_tokens": 2000,
                        }
                    ],
                    "active_backend": "claude",
                },
                "podcast_feeds": [
                    {
                        "name": "Test Podcast",
                        "rss_url": "https://example.com/feed.xml",
                        "tags": ["tech"],
                    }
                ],
            }
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert config.server.port == 8000
            assert config.mopidy.rpc_url == "http://mopidy:6680/mopidy/rpc"
            assert len(config.podcast_feeds) == 1
            assert config.podcast_feeds[0].name == "Test Podcast"
            assert len(config.llm.backends) == 1
            assert config.llm.backends[0].name == "claude"
        finally:
            temp_path.unlink()

    def test_load_nonexistent_file(self):
        """Test loading with nonexistent file falls back to defaults."""
        config = load_config(Path("/nonexistent/config.yaml"))
        # Should return default config
        assert config.server.port == 8000
        assert config.mopidy.timeout == 10

    def test_load_legacy_llm_format(self):
        """Test loading legacy single-backend LLM config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "llm": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.7,
                    "max_tokens": 2000,
                }
            }
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            # Should convert to new multi-backend format
            assert len(config.llm.backends) == 1
            assert config.llm.backends[0].name == "default"
            assert config.llm.backends[0].provider == "anthropic"
            assert config.llm.active_backend == "default"
        finally:
            temp_path.unlink()

    def test_environment_override(self, monkeypatch):
        """Test environment variables override YAML config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "server": {"port": 8000},
                "mopidy": {"rpc_url": "http://localhost:6680/mopidy/rpc"},
            }
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            # Set environment variables
            monkeypatch.setenv("PORT", "9000")
            monkeypatch.setenv("MOPIDY_RPC_URL", "http://custom:6680/mopidy/rpc")

            config = load_config(temp_path)
            assert config.server.port == 9000  # Overridden by env
            assert config.mopidy.rpc_url == "http://custom:6680/mopidy/rpc"  # Overridden
        finally:
            temp_path.unlink()


class TestGlobalConfig:
    """Tests for global config management."""

    def test_get_config_creates_default(self):
        """Test get_config creates default config if not set."""
        # Reset global config
        import media_resolver.config as config_module

        config_module._config = None

        config = get_config()
        assert config is not None
        assert isinstance(config, Config)

    def test_set_and_get_config(self):
        """Test setting and getting config."""
        custom_config = Config(
            server=ServerConfig(port=9999),
        )

        set_config(custom_config)
        retrieved = get_config()

        assert retrieved.server.port == 9999

    def test_reload_config(self, monkeypatch):
        """Test reloading configuration."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {"server": {"port": 7777}}
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            reloaded = reload_config(temp_path)
            assert reloaded.server.port == 7777
        finally:
            temp_path.unlink()


class TestSettings:
    """Tests for environment-based settings."""

    def test_settings_from_env(self, monkeypatch):
        """Test loading settings from environment."""
        monkeypatch.setenv("HOST", "127.0.0.1")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("MOPIDY_RPC_URL", "http://mopidy:6680/mopidy/rpc")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        settings = Settings()
        assert settings.host == "127.0.0.1"
        assert settings.port == 9000
        assert settings.log_level == "DEBUG"
        assert settings.mopidy_rpc_url == "http://mopidy:6680/mopidy/rpc"
        assert settings.anthropic_api_key == "test-key"

    def test_settings_optional(self):
        """Test settings with no environment variables."""
        settings = Settings()
        # All should be None by default
        assert settings.host is None
        assert settings.port is None
        assert settings.llm_provider is None
