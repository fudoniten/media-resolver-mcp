"""FastMCP server entry point for Media Resolver."""

import logging
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastmcp import FastMCP

from media_resolver.admin.routes import create_admin_app
from media_resolver.config import get_config, load_config
from media_resolver.mopidy.capabilities import get_capabilities
from media_resolver.mopidy.client import MopidyClient
from media_resolver.tools import music, playback, podcast

# Initialize structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()


async def detect_mopidy_capabilities():
    """Detect and store Mopidy backend capabilities at startup."""
    config = get_config()
    log = logger.bind(component="startup")

    try:
        log.info("detecting_mopidy_capabilities")
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            capabilities = await mopidy.detect_capabilities()
            get_capabilities().set_capabilities(capabilities)
            log.info("capabilities_detected", capabilities=capabilities)
    except Exception as e:
        log.warning("capability_detection_failed", error=str(e))
        log.info("continuing_with_limited_capabilities")


# Initialize FastMCP server
mcp = FastMCP("Media Resolver")


# Register all MCP tools


@mcp.tool()
async def get_stream_url():
    """
    Get the Icecast stream URL that Home Assistant should play.

    Returns the configured Icecast stream URL that devices can access
    to play the audio from Mopidy.
    """
    return await playback.get_stream_url()


@mcp.tool()
async def now_playing():
    """
    Get information about currently playing media.

    Returns details about what's currently playing in Mopidy, including
    title, artist/show, and playback position.
    """
    return await playback.now_playing()


@mcp.tool()
async def play_music_by_artist(
    artist: str, mode: str = "replace", limit: int = 50, shuffle: bool = True
):
    """
    Play music by a specific artist.

    Args:
        artist: Artist name to search for
        mode: 'replace' to clear queue, 'enqueue' to add to end (default: replace)
        limit: Maximum number of tracks to add (default: 50)
        shuffle: Whether to shuffle the tracks (default: True)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await music.play_music_by_artist(artist, mode, limit, shuffle)


@mcp.tool()
async def play_music_by_genre(
    genre: str, mode: str = "replace", limit: int = 50, shuffle: bool = True
):
    """
    Play music by genre.

    Args:
        genre: Genre name (e.g., 'rock', 'jazz', 'classical')
        mode: 'replace' or 'enqueue' (default: replace)
        limit: Maximum number of tracks (default: 50)
        shuffle: Whether to shuffle (default: True)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await music.play_music_by_genre(genre, mode, limit, shuffle)


@mcp.tool()
async def play_playlist(name: str, mode: str = "replace", shuffle: bool = False):
    """
    Play a playlist by name.

    Args:
        name: Playlist name or partial name
        mode: 'replace' or 'enqueue' (default: replace)
        shuffle: Whether to shuffle the playlist (default: False)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await music.play_playlist(name, mode, shuffle)


@mcp.tool()
async def play_song_search(query: str, mode: str = "replace", limit: int = 10):
    """
    Search for and play songs by title/artist keywords.

    Args:
        query: Search query (e.g., 'here comes the sun', 'beatles abbey road')
        mode: 'replace' or 'enqueue' (default: replace)
        limit: Maximum number of tracks (default: 10)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await music.play_song_search(query, mode, limit)


@mcp.tool()
async def play_podcast_latest(show: str, mode: str = "replace"):
    """
    Play the latest episode of a podcast show.

    Args:
        show: Podcast show name (must be configured in podcast feeds)
        mode: 'replace' or 'enqueue' (default: replace)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await podcast.play_podcast_latest(show, mode)


@mcp.tool()
async def play_podcast_random(show: str, mode: str = "replace", recent_count: int = 50):
    """
    Play a random episode from a podcast show.

    Args:
        show: Podcast show name
        mode: 'replace' or 'enqueue' (default: replace)
        recent_count: Number of recent episodes to sample from (default: 50)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await podcast.play_podcast_random(show, mode, recent_count)


@mcp.tool()
async def search_podcast(show: str, query: str, limit: int = 5):
    """
    Search for podcast episodes within a show.

    Returns candidates only (no playback). Use play_podcast_episode to play
    a specific result.

    Args:
        show: Podcast show name
        query: Search query (matches title and description)
        limit: Maximum number of results (default: 5)

    Returns:
        Dict with 'candidates' list of MediaCandidate objects
    """
    return await podcast.search_podcast(show, query, limit)


@mcp.tool()
async def play_podcast_episode(id: str, mode: str = "replace"):
    """
    Play a specific podcast episode by ID.

    Args:
        id: Episode ID (from search_podcast results)
        mode: 'replace' or 'enqueue' (default: replace)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await podcast.play_podcast_episode(id, mode)


@mcp.tool()
async def play_podcast_by_genre(genre: str, mode: str = "replace"):
    """
    Play latest episode from a podcast in the specified genre.

    Args:
        genre: Genre/tag name (e.g., 'news', 'comedy', 'technology')
        mode: 'replace' or 'enqueue' (default: replace)

    Returns:
        PlayPlan with stream URL and now playing information
    """
    return await podcast.play_podcast_by_genre(genre, mode)


# Create FastAPI app that combines MCP and admin UI
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    log = logger.bind(component="server")
    log.info("server_starting")

    # Load configuration
    config = load_config()
    log.info("configuration_loaded", config_summary={"llm_provider": config.llm.provider})

    # Detect Mopidy capabilities
    await detect_mopidy_capabilities()

    log.info("server_ready")

    yield

    log.info("server_shutting_down")


def create_app() -> FastAPI:
    """Create the combined FastAPI application."""
    # Create main FastAPI app
    app = FastAPI(
        title="Media Resolver MCP Server",
        description="MCP server for resolving and playing media via Mopidy",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount MCP server
    app.mount("/mcp", mcp.http_app())

    # Mount admin UI
    admin_app = create_admin_app()
    app.mount("/admin", admin_app)

    # Root redirect
    @app.get("/")
    async def root():
        return {
            "service": "Media Resolver MCP Server",
            "version": "0.1.0",
            "endpoints": {
                "mcp": "/mcp (Model Context Protocol)",
                "admin": "/admin (Web Admin UI)",
            },
        }

    return app


def main():
    """Main entry point."""
    config = load_config()

    log = logger.bind(component="main")
    log.info(
        "starting_media_resolver_mcp_server",
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level,
    )

    # Create app
    app = create_app()

    # Run with uvicorn
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()
