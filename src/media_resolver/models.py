"""Core data models for the Media Resolver MCP server."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MediaKind(str, Enum):
    """Type of media content."""

    TRACK = "track"
    ARTIST = "artist"
    PLAYLIST = "playlist"
    PODCAST_EPISODE = "podcast_episode"
    PODCAST_SHOW = "podcast_show"
    GENRE = "genre"


class PlaybackMode(str, Enum):
    """How to add content to the queue."""

    REPLACE = "replace"  # Clear queue and play
    ENQUEUE = "enqueue"  # Add to end of queue


class MediaCandidate(BaseModel):
    """A candidate media item from search/resolution."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "spotify:track:6rqhFgbbKwnb9MLmUQDhG6",
                "kind": "track",
                "title": "Here Comes the Sun",
                "subtitle": "The Beatles",
                "duration_sec": 185,
                "mopidy_uri": "spotify:track:6rqhFgbbKwnb9MLmUQDhG6",
                "score": 0.95,
                "snippet": "From Abbey Road (1969)",
            }
        }
    )

    id: str = Field(..., description="Stable identifier (Mopidy URI or URL)")
    kind: MediaKind = Field(..., description="Type of media")
    title: str = Field(..., description="Display title")
    subtitle: str | None = Field(None, description="Artist name, show name, or additional info")
    published: str | None = Field(None, description="Publication date (ISO 8601) for podcasts")
    duration_sec: int | None = Field(None, description="Duration in seconds")
    audio_url: str | None = Field(None, description="Direct playable URL if available")
    mopidy_uri: str | None = Field(None, description="Mopidy URI if applicable")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance score (0-1)")
    snippet: str | None = Field(None, description="Short description for disambiguation")


class NowPlaying(BaseModel):
    """Information about currently playing media."""

    title: str = Field(..., description="Track or episode title")
    artist_or_show: str | None = Field(None, description="Artist name or podcast show")
    kind: MediaKind = Field(..., description="Type of media")
    duration_sec: int | None = Field(None, description="Duration in seconds")
    position_sec: int | None = Field(None, description="Current playback position")
    mopidy_uri: str | None = Field(None, description="Mopidy URI")


class PlayPlan(BaseModel):
    """Plan for what to play and how."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "playback_url": "http://icecast:8000/mopidy",
                "now_playing": {
                    "title": "Here Comes the Sun",
                    "artist_or_show": "The Beatles",
                    "kind": "track",
                    "duration_sec": 185,
                },
                "requires_clarification": False,
                "total_tracks": 20,
            }
        }
    )

    playback_url: str = Field(..., description="URL for Home Assistant to play (usually Icecast)")
    now_playing: NowPlaying = Field(..., description="Information about what's playing")
    alternates: list[MediaCandidate] = Field(
        default_factory=list, description="Alternative candidates if ambiguous"
    )
    requires_clarification: bool = Field(default=False, description="Whether user input is needed")
    clarification_question: str | None = Field(
        None, description="Question to ask user for disambiguation"
    )
    total_tracks: int | None = Field(None, description="Total number of tracks queued")


class ErrorResponse(BaseModel):
    """Structured error response."""

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    retryable: bool = Field(default=False, description="Whether the operation can be retried")
    details: dict[str, Any] | None = Field(None, description="Additional error context")


class StreamInfo(BaseModel):
    """Information about the Icecast stream."""

    url: str = Field(..., description="Icecast stream URL")
    mount: str = Field(default="/mopidy", description="Icecast mount point")
    status: str = Field(default="unknown", description="Stream status (active/idle/unknown)")


# Request logging models


class RequestStatus(str, Enum):
    """Status of a request."""

    SUCCESS = "success"
    ERROR = "error"
    NEEDS_CLARIFICATION = "needs_clarification"


class LLMInteraction(BaseModel):
    """Details about LLM interaction during disambiguation."""

    provider: str = Field(..., description="LLM provider (anthropic, openai, ollama, etc.)")
    model: str = Field(..., description="Model identifier")
    prompt: str = Field(..., description="The prompt sent to the LLM")
    reasoning: str = Field(..., description="LLM's reasoning/chain of thought")
    tokens: dict[str, int] = Field(
        default_factory=dict, description="Token usage (prompt, completion)"
    )
    latency_ms: int = Field(..., description="LLM call latency in milliseconds")


class RequestLog(BaseModel):
    """Log entry for a request to the MCP server."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-01-21T12:00:00Z",
                "request_id": "req_123456",
                "tool_name": "play_music_by_artist",
                "input_params": {"artist": "The Beatles", "mode": "replace", "shuffle": True},
                "llm_interaction": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "prompt": "Rank these artists...",
                    "reasoning": "The Beatles is the most relevant match...",
                    "tokens": {"prompt": 150, "completion": 50},
                    "latency_ms": 1200,
                },
                "output": {"playback_url": "http://icecast:8000/mopidy"},
                "status": "success",
                "total_latency_ms": 2500,
                "mopidy_search_results": 5,
                "disambiguation_occurred": True,
            }
        }
    )

    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str = Field(..., description="Unique request identifier")
    tool_name: str = Field(..., description="MCP tool name")
    input_params: dict[str, Any] = Field(..., description="Input parameters to the tool")

    # LLM interaction (optional, only if disambiguation occurred)
    llm_interaction: LLMInteraction | None = Field(
        None, description="LLM interaction details if disambiguation occurred"
    )

    # Result
    output: dict[str, Any] = Field(..., description="Tool output (PlayPlan, MediaCandidate, etc.)")
    status: RequestStatus = Field(..., description="Request status")
    error_message: str | None = Field(None, description="Error message if status is error")
    total_latency_ms: int = Field(..., description="Total request latency in milliseconds")

    # Context
    mopidy_search_results: int | None = Field(
        None, description="Number of candidates from Mopidy search"
    )
    disambiguation_occurred: bool = Field(
        default=False, description="Whether LLM disambiguation was used"
    )
