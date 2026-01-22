"""Unit tests for playback tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from media_resolver.tools.playback import get_stream_url, now_playing
from media_resolver.models import NowPlaying, MediaKind
from media_resolver.config import Config, IcecastConfig, MopidyConfig


@pytest.mark.asyncio
class TestGetStreamUrl:
    """Tests for get_stream_url tool."""

    async def test_get_stream_url_success(self, sample_config):
        """Test getting stream URL successfully."""
        with patch("media_resolver.tools.playback.get_config", return_value=sample_config):
            with patch("media_resolver.tools.playback.get_request_logger") as mock_logger:
                mock_logger.return_value = MagicMock()

                result = await get_stream_url()

                assert "url" in result
                assert result["url"] == "http://localhost:8000/mopidy"
                assert result["mount"] == "/mopidy"
                assert result["status"] == "active"

    async def test_get_stream_url_error_handling(self):
        """Test error handling in get_stream_url."""
        with patch(
            "media_resolver.tools.playback.get_config", side_effect=Exception("Config error")
        ):
            with patch("media_resolver.tools.playback.get_request_logger") as mock_logger:
                mock_logger.return_value = MagicMock()

                result = await get_stream_url()

                assert "error_code" in result
                assert result["error_code"] == "stream_url_error"


@pytest.mark.asyncio
class TestNowPlaying:
    """Tests for now_playing tool."""

    async def test_now_playing_success(self, sample_config):
        """Test getting now playing info successfully."""
        mock_now_playing = NowPlaying(
            title="Test Track",
            artist_or_show="Test Artist",
            kind=MediaKind.TRACK,
            duration_sec=180,
            position_sec=45,
            mopidy_uri="spotify:track:123",
        )

        with patch("media_resolver.tools.playback.get_config", return_value=sample_config):
            with patch("media_resolver.tools.playback.MopidyClient") as mock_client_class:
                with patch("media_resolver.tools.playback.get_request_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    mock_client = AsyncMock()
                    mock_client.get_now_playing.return_value = mock_now_playing
                    mock_client.__aenter__.return_value = mock_client
                    mock_client_class.return_value = mock_client

                    result = await now_playing()

                    assert "title" in result
                    assert result["title"] == "Test Track"
                    assert result["artist_or_show"] == "Test Artist"

    async def test_now_playing_nothing_playing(self, sample_config):
        """Test now playing when nothing is playing."""
        with patch("media_resolver.tools.playback.get_config", return_value=sample_config):
            with patch("media_resolver.tools.playback.MopidyClient") as mock_client_class:
                with patch("media_resolver.tools.playback.get_request_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    mock_client = AsyncMock()
                    mock_client.get_now_playing.return_value = None
                    mock_client.__aenter__.return_value = mock_client
                    mock_client_class.return_value = mock_client

                    result = await now_playing()

                    assert "message" in result
                    assert (
                        "nothing" in result["message"].lower()
                        or "not playing" in result["message"].lower()
                    )

    async def test_now_playing_mopidy_error(self, sample_config):
        """Test error handling in now_playing."""
        with patch("media_resolver.tools.playback.get_config", return_value=sample_config):
            with patch("media_resolver.tools.playback.MopidyClient") as mock_client_class:
                with patch("media_resolver.tools.playback.get_request_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    mock_client = AsyncMock()
                    from media_resolver.mopidy.client import MopidyConnectionError

                    mock_client.get_now_playing.side_effect = MopidyConnectionError(
                        "Connection failed"
                    )
                    mock_client.__aenter__.return_value = mock_client
                    mock_client_class.return_value = mock_client

                    result = await now_playing()

                    assert "error_code" in result
                    assert "mopidy" in result["error_code"].lower()
