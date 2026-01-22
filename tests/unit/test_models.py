"""Unit tests for data models."""


import pytest

from media_resolver.models import (
    ErrorResponse,
    LLMInteraction,
    MediaCandidate,
    MediaKind,
    NowPlaying,
    PlaybackMode,
    PlayPlan,
    RequestLog,
    RequestStatus,
    StreamInfo,
)


class TestMediaKind:
    """Tests for MediaKind enum."""

    def test_media_kinds(self):
        """Test all media kinds are defined."""
        assert MediaKind.TRACK == "track"
        assert MediaKind.ARTIST == "artist"
        assert MediaKind.PLAYLIST == "playlist"
        assert MediaKind.PODCAST_EPISODE == "podcast_episode"
        assert MediaKind.PODCAST_SHOW == "podcast_show"
        assert MediaKind.GENRE == "genre"


class TestPlaybackMode:
    """Tests for PlaybackMode enum."""

    def test_playback_modes(self):
        """Test playback modes."""
        assert PlaybackMode.REPLACE == "replace"
        assert PlaybackMode.ENQUEUE == "enqueue"


class TestMediaCandidate:
    """Tests for MediaCandidate model."""

    def test_create_track_candidate(self):
        """Test creating a track candidate."""
        candidate = MediaCandidate(
            id="spotify:track:123",
            kind=MediaKind.TRACK,
            title="Here Comes the Sun",
            subtitle="The Beatles",
            duration_sec=185,
            mopidy_uri="spotify:track:123",
            score=0.95,
            snippet="From Abbey Road (1969)",
        )

        assert candidate.id == "spotify:track:123"
        assert candidate.kind == MediaKind.TRACK
        assert candidate.title == "Here Comes the Sun"
        assert candidate.subtitle == "The Beatles"
        assert candidate.duration_sec == 185
        assert candidate.score == 0.95

    def test_create_podcast_candidate(self):
        """Test creating a podcast episode candidate."""
        candidate = MediaCandidate(
            id="ep-001",
            kind=MediaKind.PODCAST_EPISODE,
            title="Episode 1: Introduction",
            subtitle="Test Podcast",
            published="2026-01-20T10:00:00",
            audio_url="https://example.com/ep1.mp3",
            duration_sec=3600,
            score=1.0,
        )

        assert candidate.kind == MediaKind.PODCAST_EPISODE
        assert candidate.audio_url == "https://example.com/ep1.mp3"
        assert candidate.published == "2026-01-20T10:00:00"

    def test_score_bounds(self):
        """Test score validation."""
        # Valid scores
        MediaCandidate(id="test", kind=MediaKind.TRACK, title="Test", score=0.0)
        MediaCandidate(id="test", kind=MediaKind.TRACK, title="Test", score=1.0)

        # Invalid scores
        with pytest.raises(ValueError):
            MediaCandidate(id="test", kind=MediaKind.TRACK, title="Test", score=1.5)

        with pytest.raises(ValueError):
            MediaCandidate(id="test", kind=MediaKind.TRACK, title="Test", score=-0.1)

    def test_optional_fields(self):
        """Test candidates with minimal required fields."""
        candidate = MediaCandidate(
            id="test",
            kind=MediaKind.TRACK,
            title="Test Track",
        )

        assert candidate.subtitle is None
        assert candidate.duration_sec is None
        assert candidate.audio_url is None
        assert candidate.score == 0.0  # Default


class TestNowPlaying:
    """Tests for NowPlaying model."""

    def test_create_now_playing(self):
        """Test creating now playing information."""
        now_playing = NowPlaying(
            title="Here Comes the Sun",
            artist_or_show="The Beatles",
            kind=MediaKind.TRACK,
            duration_sec=185,
            position_sec=45,
            mopidy_uri="spotify:track:123",
        )

        assert now_playing.title == "Here Comes the Sun"
        assert now_playing.artist_or_show == "The Beatles"
        assert now_playing.position_sec == 45

    def test_podcast_now_playing(self):
        """Test now playing for podcast."""
        now_playing = NowPlaying(
            title="Episode 1",
            artist_or_show="Test Podcast",
            kind=MediaKind.PODCAST_EPISODE,
            duration_sec=3600,
        )

        assert now_playing.kind == MediaKind.PODCAST_EPISODE
        assert now_playing.artist_or_show == "Test Podcast"


class TestPlayPlan:
    """Tests for PlayPlan model."""

    def test_create_simple_play_plan(self):
        """Test creating a basic play plan."""
        now_playing = NowPlaying(
            title="Test Track",
            kind=MediaKind.TRACK,
        )

        plan = PlayPlan(
            playback_url="http://icecast:8000/mopidy",
            now_playing=now_playing,
            total_tracks=1,
        )

        assert plan.playback_url == "http://icecast:8000/mopidy"
        assert plan.requires_clarification is False
        assert len(plan.alternates) == 0

    def test_play_plan_with_clarification(self):
        """Test play plan requiring clarification."""
        now_playing = NowPlaying(title="Test", kind=MediaKind.TRACK)
        alt1 = MediaCandidate(id="1", kind=MediaKind.TRACK, title="Track 1", score=0.9)
        alt2 = MediaCandidate(id="2", kind=MediaKind.TRACK, title="Track 2", score=0.8)

        plan = PlayPlan(
            playback_url="http://icecast:8000/mopidy",
            now_playing=now_playing,
            alternates=[alt1, alt2],
            requires_clarification=True,
            clarification_question="Which track did you mean?",
        )

        assert plan.requires_clarification is True
        assert plan.clarification_question == "Which track did you mean?"
        assert len(plan.alternates) == 2


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_create_error_response(self):
        """Test creating an error response."""
        error = ErrorResponse(
            error_code="MOPIDY_CONNECTION_ERROR",
            message="Failed to connect to Mopidy server",
            retryable=True,
            details={"url": "http://mopidy:6680"},
        )

        assert error.error_code == "MOPIDY_CONNECTION_ERROR"
        assert error.retryable is True
        assert error.details["url"] == "http://mopidy:6680"


class TestStreamInfo:
    """Tests for StreamInfo model."""

    def test_create_stream_info(self):
        """Test creating stream info."""
        stream = StreamInfo(
            url="http://icecast:8000/mopidy",
            mount="/mopidy",
            status="active",
        )

        assert stream.url == "http://icecast:8000/mopidy"
        assert stream.mount == "/mopidy"
        assert stream.status == "active"


class TestRequestLog:
    """Tests for RequestLog model."""

    def test_create_simple_request_log(self):
        """Test creating a basic request log."""
        log = RequestLog(
            request_id="req-123",
            tool_name="play_music_by_artist",
            input_params={"artist": "The Beatles", "mode": "replace"},
            output={"playback_url": "http://icecast:8000/mopidy"},
            status=RequestStatus.SUCCESS,
            total_latency_ms=1500,
        )

        assert log.request_id == "req-123"
        assert log.tool_name == "play_music_by_artist"
        assert log.status == RequestStatus.SUCCESS
        assert log.total_latency_ms == 1500
        assert log.disambiguation_occurred is False

    def test_request_log_with_llm_interaction(self):
        """Test request log with LLM disambiguation."""
        llm_interaction = LLMInteraction(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            prompt="Rank these artists...",
            reasoning="The Beatles is the most relevant match",
            tokens={"prompt": 150, "completion": 50},
            latency_ms=1200,
        )

        log = RequestLog(
            request_id="req-456",
            tool_name="play_music_by_artist",
            input_params={"artist": "beatles"},
            llm_interaction=llm_interaction,
            output={"playback_url": "http://icecast:8000/mopidy"},
            status=RequestStatus.SUCCESS,
            total_latency_ms=2500,
            mopidy_search_results=5,
            disambiguation_occurred=True,
        )

        assert log.llm_interaction is not None
        assert log.llm_interaction.provider == "anthropic"
        assert log.disambiguation_occurred is True
        assert log.mopidy_search_results == 5

    def test_request_log_with_error(self):
        """Test request log with error status."""
        log = RequestLog(
            request_id="req-789",
            tool_name="play_music_by_artist",
            input_params={"artist": "unknown"},
            output={},
            status=RequestStatus.ERROR,
            error_message="No results found",
            total_latency_ms=500,
        )

        assert log.status == RequestStatus.ERROR
        assert log.error_message == "No results found"

    def test_request_log_needs_clarification(self):
        """Test request log with needs clarification status."""
        log = RequestLog(
            request_id="req-999",
            tool_name="play_music_by_artist",
            input_params={"artist": "smith"},
            output={"requires_clarification": True},
            status=RequestStatus.NEEDS_CLARIFICATION,
            total_latency_ms=1800,
        )

        assert log.status == RequestStatus.NEEDS_CLARIFICATION


class TestLLMInteraction:
    """Tests for LLMInteraction model."""

    def test_create_llm_interaction(self):
        """Test creating LLM interaction record."""
        interaction = LLMInteraction(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            prompt="Select the best match for 'beatles'",
            reasoning="The Beatles (British rock band) is the most relevant match",
            tokens={"prompt": 200, "completion": 100},
            latency_ms=1500,
        )

        assert interaction.provider == "anthropic"
        assert interaction.model == "claude-3-5-sonnet-20241022"
        assert interaction.tokens["prompt"] == 200
        assert interaction.tokens["completion"] == 100
        assert interaction.latency_ms == 1500
