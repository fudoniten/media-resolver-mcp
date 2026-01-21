"""High-level podcast resolution logic."""

from typing import Optional

import structlog

from media_resolver.config import Config, PodcastFeed
from media_resolver.models import MediaCandidate, MediaKind
from media_resolver.podcast.rss_parser import PodcastRSSParser, RSSParserError

logger = structlog.get_logger()


class PodcastResolverError(Exception):
    """Base exception for podcast resolver errors."""

    pass


class PodcastResolver:
    """
    High-level podcast resolver.

    Manages podcast feeds and provides methods for finding and resolving episodes.
    """

    def __init__(self, config: Config):
        """
        Initialize podcast resolver.

        Args:
            config: Application configuration
        """
        self.config = config
        self.rss_parser = PodcastRSSParser()
        self.log = logger.bind(component="podcast_resolver")

        # Build feed lookup
        self._feed_map: dict[str, PodcastFeed] = {}
        for feed in config.podcast_feeds:
            # Index by name (case-insensitive)
            self._feed_map[feed.name.lower()] = feed

    def find_feed(self, show_name: str) -> Optional[PodcastFeed]:
        """
        Find podcast feed by show name.

        Args:
            show_name: Show name (case-insensitive)

        Returns:
            PodcastFeed or None if not found
        """
        return self._feed_map.get(show_name.lower())

    def find_feeds_by_genre(self, genre: str) -> list[PodcastFeed]:
        """
        Find podcast feeds by genre/tag.

        Args:
            genre: Genre name (case-insensitive)

        Returns:
            List of matching PodcastFeeds
        """
        genre_lower = genre.lower()
        matches = []

        for feed in self.config.podcast_feeds:
            if any(tag.lower() == genre_lower for tag in feed.tags):
                matches.append(feed)

        return matches

    async def get_latest_episode(self, show_name: str) -> MediaCandidate:
        """
        Get latest episode for a show.

        Args:
            show_name: Show name

        Returns:
            MediaCandidate for latest episode

        Raises:
            PodcastResolverError: If show not found or fetching fails
        """
        feed = self.find_feed(show_name)
        if not feed:
            self.log.error("show_not_found", show_name=show_name)
            raise PodcastResolverError(
                f"Podcast show '{show_name}' not found. Check configuration."
            )

        try:
            episode = await self.rss_parser.get_latest_episode(feed.rss_url, feed.name)
            if not episode:
                raise PodcastResolverError(f"No episodes found for '{show_name}'")
            return episode
        except RSSParserError as e:
            self.log.error("failed_to_get_latest", show_name=show_name, error=str(e))
            raise PodcastResolverError(f"Failed to get latest episode: {e}") from e

    async def get_random_episode(self, show_name: str, recent_count: int = 50) -> MediaCandidate:
        """
        Get random episode for a show.

        Args:
            show_name: Show name
            recent_count: Number of recent episodes to sample from

        Returns:
            MediaCandidate for random episode

        Raises:
            PodcastResolverError: If show not found or fetching fails
        """
        feed = self.find_feed(show_name)
        if not feed:
            raise PodcastResolverError(
                f"Podcast show '{show_name}' not found. Check configuration."
            )

        try:
            episode = await self.rss_parser.get_random_episode(
                feed.rss_url, feed.name, recent_count
            )
            if not episode:
                raise PodcastResolverError(f"No episodes found for '{show_name}'")
            return episode
        except RSSParserError as e:
            raise PodcastResolverError(f"Failed to get random episode: {e}") from e

    async def search_episodes(
        self, show_name: str, query: str, limit: int = 5
    ) -> list[MediaCandidate]:
        """
        Search episodes within a show.

        Args:
            show_name: Show name
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching MediaCandidates

        Raises:
            PodcastResolverError: If show not found or fetching fails
        """
        feed = self.find_feed(show_name)
        if not feed:
            raise PodcastResolverError(
                f"Podcast show '{show_name}' not found. Check configuration."
            )

        try:
            return await self.rss_parser.search_episodes(feed.rss_url, query, feed.name, limit)
        except RSSParserError as e:
            raise PodcastResolverError(f"Failed to search episodes: {e}") from e

    async def search_shows(self, query: str, limit: int = 5) -> list[MediaCandidate]:
        """
        Search for podcast shows by name.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching show MediaCandidates
        """
        query_lower = query.lower()
        matches: list[tuple[MediaCandidate, float]] = []

        for feed in self.config.podcast_feeds:
            score = 0.0
            name_lower = feed.name.lower()

            # Exact match
            if query_lower == name_lower:
                score = 1.0
            # Name contains query
            elif query_lower in name_lower:
                score = 0.8
            # Query words match
            else:
                query_words = query_lower.split()
                name_words = name_lower.split()
                matched = sum(1 for word in query_words if word in name_words)
                if matched > 0:
                    score = 0.5 * (matched / len(query_words))

            if score > 0:
                candidate = MediaCandidate(
                    id=feed.rss_url,
                    kind=MediaKind.PODCAST_SHOW,
                    title=feed.name,
                    score=score,
                    snippet=", ".join(feed.tags) if feed.tags else None,
                )
                matches.append((candidate, score))

        # Sort by score
        matches.sort(key=lambda x: x[1], reverse=True)
        return [candidate for candidate, _ in matches[:limit]]

    async def get_latest_from_genre(self, genre: str) -> Optional[MediaCandidate]:
        """
        Get latest episode from any show in a genre.

        Args:
            genre: Genre name

        Returns:
            MediaCandidate for latest episode or None if no shows in genre
        """
        feeds = self.find_feeds_by_genre(genre)
        if not feeds:
            return None

        # Get latest episode from each feed, pick the most recent overall
        latest_episode: Optional[MediaCandidate] = None
        latest_published: Optional[str] = None

        for feed in feeds:
            try:
                episode = await self.rss_parser.get_latest_episode(feed.rss_url, feed.name)
                if not episode:
                    continue

                if latest_episode is None or (
                    episode.published
                    and (latest_published is None or episode.published > latest_published)
                ):
                    latest_episode = episode
                    latest_published = episode.published
            except RSSParserError:
                # Skip feeds that fail
                continue

        return latest_episode

    def get_configured_shows(self) -> list[str]:
        """
        Get list of configured show names.

        Returns:
            List of show names
        """
        return [feed.name for feed in self.config.podcast_feeds]

    def get_configured_genres(self) -> list[str]:
        """
        Get list of configured podcast genres.

        Returns:
            List of unique genre names
        """
        genres = set()
        for feed in self.config.podcast_feeds:
            genres.update(tag.lower() for tag in feed.tags)
        return sorted(genres)
