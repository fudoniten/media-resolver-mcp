"""Unit tests for RSS feed parser."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from media_resolver.models import MediaKind
from media_resolver.podcast.rss_parser import PodcastRSSParser, RSSParserError


@pytest.mark.asyncio
class TestPodcastRSSParser:
    """Tests for PodcastRSSParser."""

    async def test_fetch_feed_success(self, sample_rss_feed):
        """Test successfully fetching and parsing RSS feed."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            feed = await parser.fetch_feed("https://example.com/feed.xml")

            assert feed is not None
            assert len(feed.entries) == 2
            assert feed.entries[0]["title"] == "Episode 1: Introduction"

    async def test_fetch_feed_http_error(self):
        """Test handling HTTP errors when fetching feed."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            import httpx

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.HTTPError("Not found")
            mock_client_class.return_value = mock_client

            with pytest.raises(RSSParserError, match="Failed to fetch RSS feed"):
                await parser.fetch_feed("https://example.com/notfound.xml")

    def test_entry_to_candidate(self, sample_podcast_entry):
        """Test converting RSS entry to MediaCandidate."""
        parser = PodcastRSSParser()

        candidate = parser.entry_to_candidate(sample_podcast_entry, show_name="Test Podcast")

        assert candidate is not None
        assert candidate.kind == MediaKind.PODCAST_EPISODE
        assert candidate.title == "Episode 1: Introduction to Testing"
        assert candidate.subtitle == "Test Podcast"
        assert candidate.audio_url == "https://example.com/episode1.mp3"
        assert candidate.id == "ep-001"
        assert candidate.score == 1.0

    def test_entry_to_candidate_no_audio(self):
        """Test entry without audio enclosure returns None."""
        parser = PodcastRSSParser()

        entry = {
            "title": "Text Only Entry",
            "enclosures": [],  # No audio
        }

        candidate = parser.entry_to_candidate(entry)

        assert candidate is None

    def test_entry_to_candidate_with_html_summary(self):
        """Test entry with HTML in summary gets cleaned."""
        parser = PodcastRSSParser()

        entry = {
            "title": "Test Episode",
            "summary": "<p>This is a <strong>test</strong> episode</p>",
            "enclosures": [{"href": "https://example.com/test.mp3", "type": "audio/mpeg"}],
            "id": "test-1",
        }

        candidate = parser.entry_to_candidate(entry, "Test Show")

        assert candidate is not None
        # HTML tags should be stripped
        assert "<p>" not in candidate.snippet
        assert "<strong>" not in candidate.snippet
        assert "This is a test episode" in candidate.snippet

    async def test_get_latest_episode(self, sample_rss_feed):
        """Test getting latest episode from feed."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            latest = await parser.get_latest_episode(
                "https://example.com/feed.xml", show_name="Test Podcast"
            )

            assert latest is not None
            assert latest.title == "Episode 1: Introduction"
            assert latest.subtitle == "Test Podcast"

    async def test_get_latest_episode_empty_feed(self):
        """Test getting latest episode from empty feed."""
        parser = PodcastRSSParser()

        empty_feed = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Empty Podcast</title>
    </channel>
</rss>"""

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = empty_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            latest = await parser.get_latest_episode("https://example.com/feed.xml")

            assert latest is None

    async def test_get_random_episode(self, sample_rss_feed):
        """Test getting random episode from feed."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            random_ep = await parser.get_random_episode("https://example.com/feed.xml")

            assert random_ep is not None
            assert random_ep.kind == MediaKind.PODCAST_EPISODE
            # Should be one of the two episodes
            assert random_ep.title in ["Episode 1: Introduction", "Episode 2: Advanced Topics"]

    async def test_search_episodes(self, sample_rss_feed):
        """Test searching episodes by query."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            # Search for "Advanced"
            results = await parser.search_episodes(
                "https://example.com/feed.xml", query="Advanced", limit=5
            )

            assert len(results) > 0
            # Should find Episode 2
            assert any("Advanced" in r.title for r in results)
            # Results should be sorted by score
            if len(results) > 1:
                assert results[0].score >= results[1].score

    async def test_search_episodes_exact_match(self, sample_rss_feed):
        """Test search with exact title match gets highest score."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            results = await parser.search_episodes(
                "https://example.com/feed.xml", query="Episode 1: Introduction", limit=5
            )

            assert len(results) > 0
            # Exact match should have score 1.0
            assert results[0].score == 1.0

    async def test_search_episodes_no_matches(self, sample_rss_feed):
        """Test search with no matches."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            results = await parser.search_episodes(
                "https://example.com/feed.xml", query="nonexistent", limit=5
            )

            assert len(results) == 0

    async def test_get_show_info(self, sample_rss_feed):
        """Test getting podcast show information."""
        parser = PodcastRSSParser()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.text = sample_rss_feed
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            show = await parser.get_show_info("https://example.com/feed.xml")

            assert show is not None
            assert show.kind == MediaKind.PODCAST_SHOW
            assert show.title == "Test Podcast"
            assert show.id == "https://example.com/feed.xml"
