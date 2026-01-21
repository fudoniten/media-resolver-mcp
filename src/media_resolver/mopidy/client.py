"""Mopidy JSON-RPC client."""

import asyncio
from typing import Any, Optional

import httpx
import structlog

from media_resolver.models import MediaCandidate, MediaKind, NowPlaying

logger = structlog.get_logger()


class MopidyError(Exception):
    """Base exception for Mopidy client errors."""

    pass


class MopidyConnectionError(MopidyError):
    """Connection to Mopidy failed."""

    pass


class MopidyRPCError(MopidyError):
    """RPC call returned an error."""

    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"Mopidy RPC Error {code}: {message}")


class MopidyClient:
    """
    Async client for Mopidy JSON-RPC API.

    Handles connection, request/response, and provides high-level methods
    for common operations.
    """

    def __init__(self, rpc_url: str, timeout: int = 10):
        """
        Initialize Mopidy client.

        Args:
            rpc_url: Mopidy JSON-RPC endpoint (e.g., http://mopidy:6680/mopidy/rpc)
            timeout: Request timeout in seconds
        """
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._request_id = 0
        self._client: Optional[httpx.AsyncClient] = None
        self._capabilities: Optional[dict[str, Any]] = None
        self.log = logger.bind(component="mopidy_client")

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    def _next_request_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def call(self, method: str, **params) -> Any:
        """
        Make a JSON-RPC call to Mopidy.

        Args:
            method: RPC method name (e.g., 'core.library.search')
            **params: Method parameters

        Returns:
            Result from the RPC call

        Raises:
            MopidyConnectionError: If connection fails
            MopidyRPCError: If RPC returns an error
        """
        if not self._client:
            raise MopidyConnectionError("Client not initialized. Use 'async with' context manager.")

        request_id = self._next_request_id()
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

        self.log.debug("mopidy_rpc_call", method=method, params=params, request_id=request_id)

        try:
            response = await self._client.post(self.rpc_url, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            self.log.error("mopidy_connection_error", error=str(e), url=self.rpc_url)
            raise MopidyConnectionError(f"Failed to connect to Mopidy: {e}") from e

        # Check for RPC error
        if "error" in data:
            error = data["error"]
            self.log.error(
                "mopidy_rpc_error",
                method=method,
                code=error.get("code"),
                message=error.get("message"),
            )
            raise MopidyRPCError(
                code=error.get("code", -1),
                message=error.get("message", "Unknown error"),
                data=error.get("data"),
            )

        result = data.get("result")
        self.log.debug("mopidy_rpc_success", method=method, result_type=type(result).__name__)
        return result

    # High-level API methods

    async def search(
        self, query: Optional[dict[str, list[str]]] = None, uris: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """
        Search library for tracks, artists, albums, etc.

        Args:
            query: Search query dict (e.g., {'artist': ['Beatles'], 'album': ['Abbey Road']})
            uris: Optional list of URI schemes to search (e.g., ['spotify:', 'local:'])

        Returns:
            List of search results from each backend
        """
        params: dict[str, Any] = {}
        if query:
            params["query"] = query
        if uris:
            params["uris"] = uris

        return await self.call("core.library.search", **params)

    async def lookup(self, uris: list[str]) -> dict[str, list[dict[str, Any]]]:
        """
        Look up tracks by URI.

        Args:
            uris: List of Mopidy URIs to look up

        Returns:
            Dict mapping URI to list of track dicts
        """
        return await self.call("core.library.lookup", uris=uris)

    async def get_playlists(self) -> list[dict[str, Any]]:
        """Get list of available playlists."""
        return await self.call("core.playlists.as_list")

    async def get_playlist(self, uri: str) -> Optional[dict[str, Any]]:
        """
        Get playlist details including tracks.

        Args:
            uri: Playlist URI

        Returns:
            Playlist dict or None if not found
        """
        return await self.call("core.playlists.lookup", uri=uri)

    async def clear_tracklist(self) -> None:
        """Clear the current tracklist."""
        await self.call("core.tracklist.clear")

    async def add_tracks(self, uris: list[str], at_position: Optional[int] = None) -> list[dict]:
        """
        Add tracks to tracklist.

        Args:
            uris: List of track URIs
            at_position: Optional position to insert at

        Returns:
            List of added track references
        """
        params: dict[str, Any] = {"uris": uris}
        if at_position is not None:
            params["at_position"] = at_position
        return await self.call("core.tracklist.add", **params)

    async def shuffle_tracklist(self) -> None:
        """Shuffle the current tracklist."""
        await self.call("core.tracklist.shuffle")

    async def play(self, tl_track: Optional[dict] = None) -> None:
        """
        Start playback.

        Args:
            tl_track: Optional specific track to play
        """
        params = {}
        if tl_track:
            params["tl_track"] = tl_track
        await self.call("core.playback.play", **params)

    async def pause(self) -> None:
        """Pause playback."""
        await self.call("core.playback.pause")

    async def stop(self) -> None:
        """Stop playback."""
        await self.call("core.playback.stop")

    async def get_current_track(self) -> Optional[dict[str, Any]]:
        """
        Get currently playing track.

        Returns:
            Track dict or None if nothing is playing
        """
        return await self.call("core.playback.get_current_track")

    async def get_state(self) -> str:
        """
        Get playback state.

        Returns:
            State string: 'playing', 'paused', or 'stopped'
        """
        return await self.call("core.playback.get_state")

    async def get_time_position(self) -> int:
        """
        Get current playback position.

        Returns:
            Position in milliseconds
        """
        return await self.call("core.playback.get_time_position")

    # Helper methods for converting Mopidy data to our models

    def track_to_candidate(self, track: dict[str, Any]) -> MediaCandidate:
        """
        Convert Mopidy track dict to MediaCandidate.

        Args:
            track: Mopidy track dict

        Returns:
            MediaCandidate instance
        """
        artists = track.get("artists", [])
        artist_name = artists[0].get("name") if artists else None

        return MediaCandidate(
            id=track.get("uri", ""),
            kind=MediaKind.TRACK,
            title=track.get("name", "Unknown Track"),
            subtitle=artist_name,
            duration_sec=track.get("length", 0) // 1000 if track.get("length") else None,
            mopidy_uri=track.get("uri"),
            score=1.0,  # Will be adjusted by disambiguation
            snippet=f"{track.get('album', {}).get('name', '')} ({track.get('date', '')})",
        )

    def artist_to_candidate(self, artist: dict[str, Any]) -> MediaCandidate:
        """Convert Mopidy artist dict to MediaCandidate."""
        return MediaCandidate(
            id=artist.get("uri", ""),
            kind=MediaKind.ARTIST,
            title=artist.get("name", "Unknown Artist"),
            mopidy_uri=artist.get("uri"),
            score=1.0,
        )

    def playlist_to_candidate(self, playlist: dict[str, Any]) -> MediaCandidate:
        """Convert Mopidy playlist dict to MediaCandidate."""
        return MediaCandidate(
            id=playlist.get("uri", ""),
            kind=MediaKind.PLAYLIST,
            title=playlist.get("name", "Unknown Playlist"),
            mopidy_uri=playlist.get("uri"),
            score=1.0,
        )

    async def get_now_playing(self) -> Optional[NowPlaying]:
        """
        Get current playback information as NowPlaying model.

        Returns:
            NowPlaying instance or None if nothing is playing
        """
        track = await self.get_current_track()
        if not track:
            return None

        state = await self.get_state()
        if state == "stopped":
            return None

        artists = track.get("artists", [])
        artist_name = artists[0].get("name") if artists else None

        position_ms = await self.get_time_position()

        return NowPlaying(
            title=track.get("name", "Unknown"),
            artist_or_show=artist_name,
            kind=MediaKind.TRACK,
            duration_sec=track.get("length", 0) // 1000 if track.get("length") else None,
            position_sec=position_ms // 1000 if position_ms else None,
            mopidy_uri=track.get("uri"),
        )

    async def detect_capabilities(self) -> dict[str, Any]:
        """
        Detect Mopidy backend capabilities.

        Returns:
            Dict of detected capabilities
        """
        if self._capabilities is not None:
            return self._capabilities

        self.log.info("detecting_mopidy_capabilities")

        capabilities = {
            "backends": [],
            "supports_genre_search": False,
            "supports_playlists": False,
            "supports_podcasts": False,
        }

        try:
            # Try to get URI schemes (indicates available backends)
            uri_schemes = await self.call("core.get_uri_schemes")
            capabilities["backends"] = uri_schemes
            self.log.info("detected_backends", backends=uri_schemes)

            # Check for playlist support
            try:
                playlists = await self.get_playlists()
                capabilities["supports_playlists"] = True
                self.log.info("playlists_supported", count=len(playlists))
            except Exception as e:
                self.log.warning("playlists_not_supported", error=str(e))

            # Check for genre search support (do a test search)
            try:
                results = await self.search(query={"genre": ["rock"]})
                if results:
                    capabilities["supports_genre_search"] = True
                    self.log.info("genre_search_supported")
            except Exception as e:
                self.log.warning("genre_search_not_supported", error=str(e))

            # Check for podcast support
            if "podcast" in uri_schemes or "podcast+http" in uri_schemes:
                capabilities["supports_podcasts"] = True
                self.log.info("podcasts_supported")

        except Exception as e:
            self.log.error("capability_detection_failed", error=str(e))

        self._capabilities = capabilities
        return capabilities
