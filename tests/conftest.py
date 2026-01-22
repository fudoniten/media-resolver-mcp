"""Shared test fixtures and configuration."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from media_resolver.config import Config, LLMConfig, LLMBackend, MopidyConfig, IcecastConfig


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    return Config(
        llm=LLMConfig(
            backends=[
                LLMBackend(
                    name="default",
                    provider="anthropic",
                    model="claude-3-5-sonnet-20241022",
                    temperature=0.7,
                    max_tokens=2000,
                )
            ],
            active_backend="default",
        ),
        mopidy=MopidyConfig(
            rpc_url="http://localhost:6680/mopidy/rpc",
            timeout=10,
        ),
        icecast=IcecastConfig(
            stream_url="http://localhost:8000/mopidy",
            mount="/mopidy",
        ),
    )


@pytest.fixture
def sample_mopidy_track():
    """Sample Mopidy track response."""
    return {
        "uri": "spotify:track:123",
        "name": "Here Comes the Sun",
        "artists": [{"name": "The Beatles", "uri": "spotify:artist:456"}],
        "album": {"name": "Abbey Road", "uri": "spotify:album:789"},
        "date": "1969",
        "length": 185000,  # milliseconds
    }


@pytest.fixture
def sample_podcast_entry():
    """Sample podcast RSS entry."""
    return {
        "title": "Episode 1: Introduction to Testing",
        "published": "Mon, 20 Jan 2026 10:00:00 GMT",
        "published_parsed": (2026, 1, 20, 10, 0, 0, 0, 0, 0),
        "author": "Test Podcast",
        "summary": "In this episode, we discuss the importance of testing.",
        "enclosures": [
            {
                "href": "https://example.com/episode1.mp3",
                "type": "audio/mpeg",
                "length": "3600",
            }
        ],
        "id": "ep-001",
    }


@pytest.fixture
def mock_mopidy_client():
    """Create a mock Mopidy client."""
    client = AsyncMock()
    client.rpc_url = "http://localhost:6680/mopidy/rpc"
    client.timeout = 10
    return client


@pytest.fixture
def mock_httpx_client():
    """Create a mock HTTPX client."""
    client = AsyncMock()
    return client


@pytest.fixture
def sample_rss_feed():
    """Sample RSS feed content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
        <title>Test Podcast</title>
        <description>A test podcast feed</description>
        <itunes:author>Test Author</itunes:author>
        <item>
            <title>Episode 1: Introduction</title>
            <description>The first episode</description>
            <pubDate>Mon, 20 Jan 2026 10:00:00 GMT</pubDate>
            <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="3600"/>
            <guid>ep-001</guid>
        </item>
        <item>
            <title>Episode 2: Advanced Topics</title>
            <description>The second episode</description>
            <pubDate>Mon, 13 Jan 2026 10:00:00 GMT</pubDate>
            <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="4200"/>
            <guid>ep-002</guid>
        </item>
    </channel>
</rss>"""
