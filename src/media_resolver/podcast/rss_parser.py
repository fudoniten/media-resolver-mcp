"""RSS feed parsing for podcasts."""

import random
from datetime import datetime

import feedparser
import httpx
import structlog
from dateutil import parser as date_parser

from media_resolver.models import MediaCandidate, MediaKind

logger = structlog.get_logger()


class RSSParserError(Exception):
    """Base exception for RSS parsing errors."""

    pass


class PodcastRSSParser:
    """
    Parser for podcast RSS feeds.

    Handles fetching and parsing RSS feeds to extract episode information.
    """

    def __init__(self, timeout: int = 10):
        """
        Initialize RSS parser.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.log = logger.bind(component="rss_parser")

    async def fetch_feed(self, rss_url: str) -> feedparser.FeedParserDict:
        """
        Fetch and parse an RSS feed.

        Args:
            rss_url: URL of the RSS feed

        Returns:
            Parsed feed dict

        Raises:
            RSSParserError: If fetching or parsing fails
        """
        self.log.debug("fetching_feed", url=rss_url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(rss_url)
                response.raise_for_status()
                feed_content = response.text
        except httpx.HTTPError as e:
            self.log.error("feed_fetch_error", url=rss_url, error=str(e))
            raise RSSParserError(f"Failed to fetch RSS feed: {e}") from e

        # Parse with feedparser
        feed = feedparser.parse(feed_content)

        if feed.bozo:
            # Feed has parsing errors
            self.log.warning("feed_parse_warning", url=rss_url, error=feed.bozo_exception)

        if not feed.entries:
            self.log.warning("empty_feed", url=rss_url)

        self.log.info("feed_fetched", url=rss_url, entries=len(feed.entries))
        return feed

    def entry_to_candidate(
        self, entry: dict, show_name: str | None = None
    ) -> MediaCandidate | None:
        """
        Convert RSS feed entry to MediaCandidate.

        Args:
            entry: Feed entry dict from feedparser
            show_name: Optional show name (if not in entry)

        Returns:
            MediaCandidate or None if entry doesn't have required fields
        """
        # Get audio URL from enclosures
        audio_url = None
        duration_sec = None

        for enclosure in entry.get("enclosures", []):
            if enclosure.get("type", "").startswith("audio/"):
                audio_url = enclosure.get("href")
                # Try to get duration
                if "length" in enclosure:
                    try:
                        duration_sec = int(enclosure["length"])
                    except (ValueError, TypeError):
                        pass
                break

        if not audio_url:
            # No audio enclosure found
            return None

        # Extract metadata
        title = entry.get("title", "Unknown Episode")
        subtitle = show_name or entry.get("itunes_author") or entry.get("author")

        # Parse published date
        published = None
        if "published_parsed" in entry and entry.get("published_parsed"):
            try:
                dt = datetime(*entry["published_parsed"][:6])
                published = dt.isoformat()
            except (TypeError, ValueError):
                pass

        if not published and "published" in entry:
            try:
                dt = date_parser.parse(entry["published"])
                published = dt.isoformat()
            except Exception:
                pass

        # Get description/summary
        snippet = entry.get("summary", entry.get("description", ""))
        # Clean HTML tags if present (basic cleanup)
        if snippet:
            import re

            snippet = re.sub(r"<[^>]+>", "", snippet)
            snippet = snippet[:200]  # Limit length

        # Use audio URL as ID (some feeds don't have GUIDs)
        episode_id = entry.get("id", entry.get("guid", audio_url))

        return MediaCandidate(
            id=episode_id,
            kind=MediaKind.PODCAST_EPISODE,
            title=title,
            subtitle=subtitle,
            published=published,
            duration_sec=duration_sec,
            audio_url=audio_url,
            score=1.0,
            snippet=snippet,
        )

    async def get_latest_episode(
        self, rss_url: str, show_name: str | None = None
    ) -> MediaCandidate | None:
        """
        Get the latest episode from a podcast feed.

        Args:
            rss_url: RSS feed URL
            show_name: Optional show name

        Returns:
            MediaCandidate for latest episode or None if feed is empty
        """
        feed = await self.fetch_feed(rss_url)

        if not feed.entries:
            return None

        # First entry is usually the latest
        latest_entry = feed.entries[0]

        # But let's verify by checking published dates
        for entry in feed.entries[:5]:  # Check first 5
            entry_date = entry.get("published_parsed")
            latest_date = latest_entry.get("published_parsed")

            if entry_date and latest_date and entry_date > latest_date:
                latest_entry = entry

        return self.entry_to_candidate(latest_entry, show_name or feed.feed.get("title"))

    async def get_random_episode(
        self, rss_url: str, show_name: str | None = None, recent_count: int = 50
    ) -> MediaCandidate | None:
        """
        Get a random episode from recent episodes.

        Args:
            rss_url: RSS feed URL
            show_name: Optional show name
            recent_count: Number of recent episodes to sample from

        Returns:
            MediaCandidate for random episode or None if feed is empty
        """
        feed = await self.fetch_feed(rss_url)

        if not feed.entries:
            return None

        # Sample from recent episodes
        sample_entries = feed.entries[: min(recent_count, len(feed.entries))]
        random_entry = random.choice(sample_entries)

        return self.entry_to_candidate(random_entry, show_name or feed.feed.get("title"))

    async def search_episodes(
        self, rss_url: str, query: str, show_name: str | None = None, limit: int = 5
    ) -> list[MediaCandidate]:
        """
        Search episodes by title and description.

        Args:
            rss_url: RSS feed URL
            query: Search query
            show_name: Optional show name
            limit: Maximum number of results

        Returns:
            List of matching MediaCandidates, sorted by relevance
        """
        feed = await self.fetch_feed(rss_url)

        if not feed.entries:
            return []

        query_lower = query.lower()
        show_title = show_name or feed.feed.get("title")
        matches: list[tuple[MediaCandidate, float]] = []

        for entry in feed.entries:
            candidate = self.entry_to_candidate(entry, show_title)
            if not candidate:
                continue

            # Calculate relevance score
            score = 0.0

            title_lower = candidate.title.lower()
            snippet_lower = (candidate.snippet or "").lower()

            # Exact title match
            if query_lower == title_lower:
                score = 1.0
            # Title contains query
            elif query_lower in title_lower:
                score = 0.8
            # Description contains query
            elif query_lower in snippet_lower:
                score = 0.5
            # Word match
            else:
                query_words = query_lower.split()
                title_words = title_lower.split()
                snippet_words = snippet_lower.split()

                matched_words = sum(
                    1 for word in query_words if word in title_words or word in snippet_words
                )

                if matched_words > 0:
                    score = 0.3 * (matched_words / len(query_words))

            if score > 0:
                candidate.score = score
                matches.append((candidate, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        # Return top N
        return [candidate for candidate, _ in matches[:limit]]

    async def get_show_info(self, rss_url: str) -> MediaCandidate | None:
        """
        Get podcast show information.

        Args:
            rss_url: RSS feed URL

        Returns:
            MediaCandidate representing the show
        """
        feed = await self.fetch_feed(rss_url)

        if not feed.feed:
            return None

        title = feed.feed.get("title", "Unknown Podcast")
        subtitle = feed.feed.get("author", feed.feed.get("itunes_author"))
        description = feed.feed.get("subtitle", feed.feed.get("description", ""))

        return MediaCandidate(
            id=rss_url,
            kind=MediaKind.PODCAST_SHOW,
            title=title,
            subtitle=subtitle,
            snippet=description[:200] if description else None,
            score=1.0,
        )
