"""Configuration management for Media Resolver."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMBackend(BaseModel):
    """Individual LLM backend configuration."""

    name: str = Field(
        ..., description="Unique name for this backend (e.g., 'claude-sonnet', 'gpt4')"
    )
    provider: str = Field(
        ...,
        description="LLM provider: anthropic, openai, ollama, azure, cohere",
    )
    model: str = Field(..., description="Model identifier")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=2000, ge=1, description="Maximum tokens to generate")
    base_url: str | None = Field(None, description="Base URL for local/Ollama deployments")
    api_key: str | None = Field(None, description="API key (can use env var instead)")


class LLMConfig(BaseModel):
    """LLM provider configuration with support for multiple backends."""

    backends: list[LLMBackend] = Field(
        default_factory=list,
        description="List of available LLM backends",
    )
    active_backend: str = Field(
        default="default",
        description="Name of the currently active backend",
    )

    def get_active_backend(self) -> LLMBackend | None:
        """Get the currently active backend configuration."""
        for backend in self.backends:
            if backend.name == self.active_backend:
                return backend
        # Fallback to first backend if active not found
        return self.backends[0] if self.backends else None

    # Legacy single backend support (for backwards compatibility during migration)
    provider: str | None = Field(
        None,
        description="DEPRECATED: Use backends list instead. LLM provider: anthropic, openai, ollama, azure, cohere",
    )
    model: str | None = Field(
        None, description="DEPRECATED: Use backends list instead. Model identifier"
    )
    temperature: float | None = Field(
        None, ge=0.0, le=2.0, description="DEPRECATED: Sampling temperature"
    )
    max_tokens: int | None = Field(
        None, ge=1, description="DEPRECATED: Maximum tokens to generate"
    )
    base_url: str | None = Field(
        None, description="DEPRECATED: Base URL for local/Ollama deployments"
    )
    api_key: str | None = Field(
        None, description="DEPRECATED: API key (can use env var instead)"
    )

    def model_post_init(self, __context) -> None:
        """Convert legacy single backend config to new multi-backend format."""
        super().model_post_init(__context)

        # If using legacy format, convert to new format
        if self.provider and not self.backends:
            legacy_backend = LLMBackend(
                name="default",
                provider=self.provider,
                model=self.model or "claude-3-5-sonnet-20241022",
                temperature=self.temperature if self.temperature is not None else 0.7,
                max_tokens=self.max_tokens or 2000,
                base_url=self.base_url,
                api_key=self.api_key,
            )
            self.backends = [legacy_backend]
            self.active_backend = "default"


class MopidyConfig(BaseModel):
    """Mopidy connection configuration."""

    rpc_url: str = Field(
        default="http://localhost:6680/mopidy/rpc", description="Mopidy JSON-RPC endpoint"
    )
    timeout: int = Field(default=10, ge=1, description="Request timeout in seconds")


class IcecastConfig(BaseModel):
    """Icecast streaming configuration."""

    stream_url: str = Field(
        default="http://localhost:8000/mopidy",
        description="Icecast stream URL accessible from playback devices",
    )
    mount: str = Field(default="/mopidy", description="Icecast mount point")


class PodcastFeed(BaseModel):
    """Podcast feed configuration."""

    name: str = Field(..., description="Display name of the podcast show")
    rss_url: str = Field(..., description="RSS feed URL")
    tags: list[str] = Field(default_factory=list, description="Tags/genres for this show")


class GenreMapping(BaseModel):
    """Genre to content mapping."""

    genre: str = Field(..., description="Genre name")
    playlists: list[str] = Field(
        default_factory=list, description="Playlist names or URIs for this genre"
    )
    podcast_shows: list[str] = Field(
        default_factory=list, description="Podcast show names for this genre"
    )


class ServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")


class Config(BaseModel):
    """Main application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    mopidy: MopidyConfig = Field(default_factory=MopidyConfig)
    icecast: IcecastConfig = Field(default_factory=IcecastConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # Podcast configuration
    podcast_feeds: list[PodcastFeed] = Field(
        default_factory=list, description="List of podcast feeds to monitor"
    )

    # Genre mappings
    genre_mappings: list[GenreMapping] = Field(
        default_factory=list, description="Genre to content mappings"
    )

    # Request history
    max_request_history: int = Field(
        default=500, ge=10, description="Maximum number of requests to keep in history"
    )


class Settings(BaseSettings):
    """Environment-based settings (overrides YAML config)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Server
    host: str | None = None
    port: int | None = None
    log_level: str | None = None

    # Mopidy
    mopidy_rpc_url: str | None = None
    mopidy_timeout: int | None = None

    # Icecast
    icecast_stream_url: str | None = None

    # LLM
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    llm_max_tokens: int | None = None
    ollama_base_url: str | None = None

    # API Keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # History
    max_request_history: int | None = None


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from YAML file and environment variables.

    Environment variables override YAML settings.

    Args:
        config_path: Path to YAML config file. If None, uses default locations.

    Returns:
        Loaded configuration
    """
    # Try default locations
    if config_path is None:
        possible_paths = [
            Path("config/config.yaml"),
            Path("config.yaml"),
            Path("/etc/media-resolver/config.yaml"),
        ]
        for path in possible_paths:
            if path.exists():
                config_path = path
                break

    # Load base config from YAML
    config_dict: dict[str, Any] = {}
    if config_path and config_path.exists():
        with open(config_path) as f:
            config_dict = yaml.safe_load(f) or {}

    # Load environment settings
    env_settings = Settings()

    # Apply environment overrides
    if env_settings.host:
        config_dict.setdefault("server", {})["host"] = env_settings.host
    if env_settings.port:
        config_dict.setdefault("server", {})["port"] = env_settings.port
    if env_settings.log_level:
        config_dict.setdefault("server", {})["log_level"] = env_settings.log_level

    if env_settings.mopidy_rpc_url:
        config_dict.setdefault("mopidy", {})["rpc_url"] = env_settings.mopidy_rpc_url
    if env_settings.mopidy_timeout:
        config_dict.setdefault("mopidy", {})["timeout"] = env_settings.mopidy_timeout

    if env_settings.icecast_stream_url:
        config_dict.setdefault("icecast", {})["stream_url"] = env_settings.icecast_stream_url

    # Handle legacy LLM environment variables (backwards compatibility)
    if env_settings.llm_provider:
        config_dict.setdefault("llm", {})["provider"] = env_settings.llm_provider
    if env_settings.llm_model:
        config_dict.setdefault("llm", {})["model"] = env_settings.llm_model
    if env_settings.llm_temperature is not None:
        config_dict.setdefault("llm", {})["temperature"] = env_settings.llm_temperature
    if env_settings.llm_max_tokens:
        config_dict.setdefault("llm", {})["max_tokens"] = env_settings.llm_max_tokens
    if env_settings.ollama_base_url:
        config_dict.setdefault("llm", {})["base_url"] = env_settings.ollama_base_url

    # Set API keys from environment (always set these for LangChain)
    if env_settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = env_settings.anthropic_api_key
    if env_settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = env_settings.openai_api_key

    if env_settings.max_request_history:
        config_dict["max_request_history"] = env_settings.max_request_history

    return Config(**config_dict)


# Global config instance (will be set at startup)
_config: Config | None = None


def get_config() -> Config:
    """Get the current configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the configuration instance (useful for testing or runtime updates)."""
    global _config
    _config = config


def reload_config(config_path: Path | None = None) -> Config:
    """Reload configuration from disk."""
    global _config
    _config = load_config(config_path)
    return _config
