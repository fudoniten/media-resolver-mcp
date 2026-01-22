"""Mopidy backend capabilities detection and storage."""

from typing import Any


class MopidyCapabilities:
    """
    Stores and provides access to detected Mopidy backend capabilities.

    This is a singleton that stores capabilities detected at startup,
    allowing tools to check what features are available.
    """

    def __init__(self):
        """Initialize empty capabilities."""
        self._capabilities: dict[str, Any] = {}

    def set_capabilities(self, capabilities: dict[str, Any]) -> None:
        """
        Set the detected capabilities.

        Args:
            capabilities: Dict of capability information from Mopidy
        """
        self._capabilities = capabilities

    def get_capabilities(self) -> dict[str, Any]:
        """
        Get all detected capabilities.

        Returns:
            Dict of capabilities
        """
        return self._capabilities

    def supports_genre_search(self) -> bool:
        """
        Check if Mopidy supports genre search.

        Returns:
            True if genre search is supported
        """
        return self._capabilities.get("supports_genre_search", False)

    def supports_playlists(self) -> bool:
        """
        Check if Mopidy supports playlists.

        Returns:
            True if playlists are supported
        """
        return self._capabilities.get("supports_playlists", False)

    def supports_podcasts(self) -> bool:
        """
        Check if Mopidy supports podcast playback.

        Returns:
            True if podcast playback is supported
        """
        return self._capabilities.get("supports_podcasts", False)

    def get_backends(self) -> list[str]:
        """
        Get list of available Mopidy backend URI schemes.

        Returns:
            List of URI schemes (e.g., ['spotify', 'local', 'podcast'])
        """
        return self._capabilities.get("backends", [])


# Global singleton instance
_capabilities = MopidyCapabilities()


def get_capabilities() -> MopidyCapabilities:
    """
    Get the global capabilities singleton.

    Returns:
        MopidyCapabilities instance
    """
    return _capabilities
