"""Unit tests for Mopidy client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from media_resolver.models import MediaKind
from media_resolver.mopidy.client import (
    MopidyClient,
    MopidyConnectionError,
    MopidyRPCError,
)


class TestMopidyClientInit:
    """Tests for MopidyClient initialization."""

    def test_init(self):
        """Test client initialization."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc", timeout=15)
        assert client.rpc_url == "http://localhost:6680/mopidy/rpc"
        assert client.timeout == 15
        assert client._request_id == 0
        assert client._client is None

    def test_next_request_id(self):
        """Test request ID incrementing."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")
        assert client._next_request_id() == 1
        assert client._next_request_id() == 2
        assert client._next_request_id() == 3


@pytest.mark.asyncio
class TestMopidyClientContextManager:
    """Tests for async context manager."""

    async def test_context_manager(self):
        """Test async context manager creates and closes client."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        assert client._client is None

        async with client:
            assert client._client is not None

        # Client should be closed after exiting context


@pytest.mark.asyncio
class TestMopidyClientCalls:
    """Tests for RPC calls."""

    async def test_call_without_client(self):
        """Test calling RPC without initializing client."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        with pytest.raises(MopidyConnectionError, match="Client not initialized"):
            await client.call("core.playback.get_state")

    async def test_successful_call(self):
        """Test successful RPC call."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "playing"}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        result = await client.call("core.playback.get_state")

        assert result == "playing"
        mock_http_client.post.assert_called_once()

    async def test_call_with_params(self):
        """Test RPC call with parameters."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": []}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        await client.call("core.library.search", query={"artist": ["Beatles"]})

        # Verify params were passed
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "core.library.search"
        assert payload["params"]["query"] == {"artist": ["Beatles"]}

    async def test_connection_error(self):
        """Test handling connection errors."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_http_client = AsyncMock()
        import httpx

        mock_http_client.post.side_effect = httpx.ConnectError("Connection refused")

        client._client = mock_http_client

        with pytest.raises(MopidyConnectionError, match="Failed to connect"):
            await client.call("core.playback.get_state")

    async def test_rpc_error(self):
        """Test handling RPC errors."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found", "data": None},
        }

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        with pytest.raises(MopidyRPCError) as exc_info:
            await client.call("core.invalid.method")

        assert exc_info.value.code == -32601
        assert "Method not found" in exc_info.value.message


@pytest.mark.asyncio
class TestMopidyClientHighLevel:
    """Tests for high-level client methods."""

    async def test_search(self):
        """Test library search."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": []}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        results = await client.search(query={"artist": ["Beatles"]})

        assert isinstance(results, list)

    async def test_get_playlists(self):
        """Test getting playlists."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [{"uri": "playlist:1", "name": "Rock Classics"}],
        }

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        playlists = await client.get_playlists()

        assert len(playlists) == 1
        assert playlists[0]["name"] == "Rock Classics"

    async def test_clear_tracklist(self):
        """Test clearing tracklist."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": None}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        await client.clear_tracklist()

        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "core.tracklist.clear"

    async def test_play(self):
        """Test starting playback."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": None}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        client._client = mock_http_client

        await client.play()

        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "core.playback.play"


class TestMopidyClientConverters:
    """Tests for data conversion methods."""

    def test_track_to_candidate(self, sample_mopidy_track):
        """Test converting Mopidy track to MediaCandidate."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        candidate = client.track_to_candidate(sample_mopidy_track)

        assert candidate.id == "spotify:track:123"
        assert candidate.kind == MediaKind.TRACK
        assert candidate.title == "Here Comes the Sun"
        assert candidate.subtitle == "The Beatles"
        assert candidate.duration_sec == 185  # Converted from ms
        assert candidate.mopidy_uri == "spotify:track:123"

    def test_track_to_candidate_missing_fields(self):
        """Test converting track with missing optional fields."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        track = {"uri": "test:track:1", "name": "Test Track"}

        candidate = client.track_to_candidate(track)

        assert candidate.title == "Test Track"
        assert candidate.subtitle is None
        assert candidate.duration_sec is None

    def test_artist_to_candidate(self):
        """Test converting Mopidy artist to MediaCandidate."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        artist = {"uri": "spotify:artist:456", "name": "The Beatles"}

        candidate = client.artist_to_candidate(artist)

        assert candidate.kind == MediaKind.ARTIST
        assert candidate.title == "The Beatles"
        assert candidate.mopidy_uri == "spotify:artist:456"

    def test_playlist_to_candidate(self):
        """Test converting Mopidy playlist to MediaCandidate."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        playlist = {"uri": "spotify:playlist:789", "name": "Rock Classics"}

        candidate = client.playlist_to_candidate(playlist)

        assert candidate.kind == MediaKind.PLAYLIST
        assert candidate.title == "Rock Classics"
        assert candidate.mopidy_uri == "spotify:playlist:789"


@pytest.mark.asyncio
class TestMopidyClientNowPlaying:
    """Tests for now playing functionality."""

    async def test_get_now_playing(self, sample_mopidy_track):
        """Test getting current playback info."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        # Mock responses for get_current_track, get_state, get_time_position
        client.get_current_track = AsyncMock(return_value=sample_mopidy_track)
        client.get_state = AsyncMock(return_value="playing")
        client.get_time_position = AsyncMock(return_value=45000)  # 45 seconds in ms

        now_playing = await client.get_now_playing()

        assert now_playing is not None
        assert now_playing.title == "Here Comes the Sun"
        assert now_playing.artist_or_show == "The Beatles"
        assert now_playing.duration_sec == 185
        assert now_playing.position_sec == 45

    async def test_get_now_playing_stopped(self):
        """Test now playing when stopped."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        client.get_current_track = AsyncMock(return_value={"uri": "test", "name": "Test"})
        client.get_state = AsyncMock(return_value="stopped")

        now_playing = await client.get_now_playing()

        assert now_playing is None

    async def test_get_now_playing_no_track(self):
        """Test now playing when no track is playing."""
        client = MopidyClient("http://localhost:6680/mopidy/rpc")

        client.get_current_track = AsyncMock(return_value=None)

        now_playing = await client.get_now_playing()

        assert now_playing is None
