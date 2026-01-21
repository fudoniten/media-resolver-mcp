"""Podcast-related MCP tools."""

import time
from typing import Optional

import structlog

from media_resolver.config import get_config
from media_resolver.disambiguation.service import DisambiguationService
from media_resolver.models import MediaCandidate, MediaKind, NowPlaying, PlaybackMode, PlayPlan
from media_resolver.mopidy.client import MopidyClient, MopidyError
from media_resolver.podcast.resolver import PodcastResolver, PodcastResolverError
from media_resolver.request_logger import RequestStatus, get_request_logger

logger = structlog.get_logger()


async def play_podcast_latest(show: str, mode: str = "replace") -> dict:
    """
    Play the latest episode of a podcast show.

    Args:
        show: Podcast show name
        mode: Playback mode ('replace' or 'enqueue')

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_podcast_latest", show=show)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"show": show, "mode": mode}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_podcast_latest",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        resolver = PodcastResolver(config)
        episode = await resolver.get_latest_episode(show)

        log.info("got_latest_episode", title=episode.title)

        # Play via Mopidy if it has URI, otherwise note this is for direct play
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            # Try to add audio URL to Mopidy (works if Mopidy supports HTTP streams)
            if episode.audio_url:
                await mopidy.add_tracks([episode.audio_url])
                await mopidy.play()

            # Build result
            now_playing = NowPlaying(
                title=episode.title,
                artist_or_show=episode.subtitle,
                kind=MediaKind.PODCAST_EPISODE,
                duration_sec=episode.duration_sec,
            )

            plan = PlayPlan(
                playback_url=config.icecast.stream_url, now_playing=now_playing, total_tracks=1
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_podcast_latest",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
            )

            log.info("podcast_latest_started", show=show, episode=episode.title)
            return plan.model_dump()

    except PodcastResolverError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("podcast_resolver_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_latest",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "podcast_error", "message": str(e), "retryable": False}

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_latest",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "mopidy_error", "message": str(e), "retryable": True}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("unexpected_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_latest",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def play_podcast_random(show: str, mode: str = "replace", recent_count: int = 50) -> dict:
    """
    Play a random episode from a podcast show.

    Args:
        show: Podcast show name
        mode: Playback mode ('replace' or 'enqueue')
        recent_count: Number of recent episodes to sample from

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_podcast_random", show=show)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"show": show, "mode": mode, "recent_count": recent_count}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_podcast_random",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        resolver = PodcastResolver(config)
        episode = await resolver.get_random_episode(show, recent_count)

        log.info("got_random_episode", title=episode.title)

        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            if episode.audio_url:
                await mopidy.add_tracks([episode.audio_url])
                await mopidy.play()

            now_playing = NowPlaying(
                title=episode.title,
                artist_or_show=episode.subtitle,
                kind=MediaKind.PODCAST_EPISODE,
                duration_sec=episode.duration_sec,
            )

            plan = PlayPlan(
                playback_url=config.icecast.stream_url, now_playing=now_playing, total_tracks=1
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_podcast_random",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
            )

            log.info("podcast_random_started", show=show, episode=episode.title)
            return plan.model_dump()

    except PodcastResolverError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("podcast_resolver_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_random",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "podcast_error", "message": str(e), "retryable": False}

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_random",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "mopidy_error", "message": str(e), "retryable": True}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("unexpected_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_random",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def search_podcast(show: str, query: str, limit: int = 5) -> dict:
    """
    Search for podcast episodes within a show.

    Args:
        show: Podcast show name
        query: Search query
        limit: Maximum number of results

    Returns:
        Dict with candidates list
    """
    start_time = time.time()
    log = logger.bind(tool="search_podcast", show=show, query=query)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"show": show, "query": query, "limit": limit}

    try:
        resolver = PodcastResolver(config)
        candidates = await resolver.search_episodes(show, query, limit)

        log.info("found_episodes", count=len(candidates))

        # Use LLM to rank if we have multiple candidates
        llm_interaction = None
        if len(candidates) > 1:
            disambiguator = DisambiguationService()
            ranked, llm_interaction = await disambiguator.disambiguate(
                query=query,
                candidates=candidates,
                context={"search_type": "podcast_episode", "show": show},
                top_k=limit,
            )
            if ranked:
                candidates = ranked

        result = {"candidates": [c.model_dump() for c in candidates]}

        latency_ms = int((time.time() - start_time) * 1000)
        request_logger.log_request(
            tool_name="search_podcast",
            input_params=input_params,
            output=result,
            status=RequestStatus.SUCCESS,
            total_latency_ms=latency_ms,
            llm_interaction=llm_interaction,
        )

        return result

    except PodcastResolverError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("podcast_resolver_error", error=str(e))
        request_logger.log_request(
            tool_name="search_podcast",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "podcast_error", "message": str(e), "retryable": False}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("unexpected_error", error=str(e))
        request_logger.log_request(
            tool_name="search_podcast",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def play_podcast_episode(id: str, mode: str = "replace") -> dict:
    """
    Play a specific podcast episode by ID.

    Args:
        id: Episode ID (from search results)
        mode: Playback mode ('replace' or 'enqueue')

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_podcast_episode", id=id)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"id": id, "mode": mode}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_podcast_episode",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        # ID should be a URL or URI we can play
        audio_url = id

        log.info("playing_episode_by_id")

        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            await mopidy.add_tracks([audio_url])
            await mopidy.play()

            # Get now playing
            now_playing = await mopidy.get_now_playing()
            if not now_playing:
                now_playing = NowPlaying(
                    title="Podcast Episode", artist_or_show="Unknown", kind=MediaKind.PODCAST_EPISODE
                )

            plan = PlayPlan(
                playback_url=config.icecast.stream_url, now_playing=now_playing, total_tracks=1
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_podcast_episode",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
            )

            log.info("podcast_episode_started")
            return plan.model_dump()

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_episode",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "mopidy_error", "message": str(e), "retryable": True}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("unexpected_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_episode",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def play_podcast_by_genre(genre: str, mode: str = "replace") -> dict:
    """
    Play latest episode from a podcast in the specified genre.

    Args:
        genre: Genre name (e.g., 'news', 'comedy', 'technology')
        mode: Playback mode ('replace' or 'enqueue')

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_podcast_by_genre", genre=genre)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"genre": genre, "mode": mode}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_podcast_by_genre",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        resolver = PodcastResolver(config)
        episode = await resolver.get_latest_from_genre(genre)

        if not episode:
            error_msg = f"No podcasts found for genre '{genre}'. Check configuration."
            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_podcast_by_genre",
                input_params=input_params,
                output={},
                status=RequestStatus.ERROR,
                total_latency_ms=latency_ms,
                error_message=error_msg,
            )
            return {"error_code": "genre_not_found", "message": error_msg, "retryable": False}

        log.info("got_genre_episode", title=episode.title, show=episode.subtitle)

        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            if episode.audio_url:
                await mopidy.add_tracks([episode.audio_url])
                await mopidy.play()

            now_playing = NowPlaying(
                title=episode.title,
                artist_or_show=episode.subtitle,
                kind=MediaKind.PODCAST_EPISODE,
                duration_sec=episode.duration_sec,
            )

            plan = PlayPlan(
                playback_url=config.icecast.stream_url, now_playing=now_playing, total_tracks=1
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_podcast_by_genre",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
            )

            log.info("podcast_genre_started", genre=genre, episode=episode.title)
            return plan.model_dump()

    except PodcastResolverError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("podcast_resolver_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_by_genre",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "podcast_error", "message": str(e), "retryable": False}

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_by_genre",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "mopidy_error", "message": str(e), "retryable": True}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("unexpected_error", error=str(e))
        request_logger.log_request(
            tool_name="play_podcast_by_genre",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}
