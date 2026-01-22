"""Music-related MCP tools."""

import time

import structlog

from media_resolver.config import get_config
from media_resolver.disambiguation.service import DisambiguationService
from media_resolver.models import MediaCandidate, MediaKind, NowPlaying, PlaybackMode, PlayPlan
from media_resolver.mopidy.capabilities import get_capabilities
from media_resolver.mopidy.client import MopidyClient, MopidyError
from media_resolver.request_logger import RequestStatus, get_request_logger

logger = structlog.get_logger()


async def play_music_by_artist(
    artist: str, mode: str = "replace", limit: int = 50, shuffle: bool = True
) -> dict:
    """
    Play music by artist.

    Args:
        artist: Artist name to search for
        mode: Playback mode ('replace' or 'enqueue')
        limit: Maximum number of tracks
        shuffle: Whether to shuffle tracks

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_music_by_artist", artist=artist)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"artist": artist, "mode": mode, "limit": limit, "shuffle": shuffle}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}. Must be 'replace' or 'enqueue'"
        request_logger.log_request(
            tool_name="play_music_by_artist",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            # Search for artist
            log.info("searching_artist")
            results = await mopidy.search(query={"artist": [artist]})

            # Collect artist candidates from all backends
            artist_candidates: list[MediaCandidate] = []
            for backend_result in results:
                for artist_result in backend_result.get("artists", []):
                    candidate = mopidy.artist_to_candidate(artist_result)
                    artist_candidates.append(candidate)

            if not artist_candidates:
                error_msg = f"No artist found matching '{artist}'"
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_music_by_artist",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                    mopidy_search_results=0,
                )
                return {"error_code": "not_found", "message": error_msg, "retryable": False}

            log.info("found_artists", count=len(artist_candidates))

            # Disambiguate if multiple artists
            llm_interaction = None
            selected_artist = artist_candidates[0]

            if len(artist_candidates) > 1:
                log.info("disambiguating_artists")
                disambiguator = DisambiguationService()
                ranked, llm_interaction = await disambiguator.disambiguate(
                    query=artist,
                    candidates=artist_candidates,
                    context={"search_type": "artist"},
                    top_k=1,
                )
                if ranked:
                    selected_artist = ranked[0]

            # Get tracks for artist (search for tracks by this artist)
            log.info("fetching_tracks", artist_uri=selected_artist.mopidy_uri)
            track_results = await mopidy.search(query={"artist": [selected_artist.title]})

            # Collect tracks
            tracks = []
            for backend_result in track_results:
                tracks.extend(backend_result.get("tracks", []))

            if not tracks:
                error_msg = f"No tracks found for artist '{selected_artist.title}'"
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_music_by_artist",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                    llm_interaction=llm_interaction,
                    mopidy_search_results=len(artist_candidates),
                )
                return {"error_code": "no_tracks", "message": error_msg, "retryable": False}

            # Limit tracks
            tracks = tracks[:limit]
            track_uris = [track["uri"] for track in tracks]

            log.info("queuing_tracks", count=len(track_uris))

            # Clear and add to queue
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            await mopidy.add_tracks(track_uris)

            if shuffle:
                await mopidy.shuffle_tracklist()

            await mopidy.play()

            # Get now playing
            now_playing = await mopidy.get_now_playing()
            if not now_playing:
                now_playing = NowPlaying(
                    title=tracks[0].get("name", "Unknown"),
                    artist_or_show=selected_artist.title,
                    kind=MediaKind.TRACK,
                )

            # Build result
            plan = PlayPlan(
                playback_url=config.icecast.stream_url,
                now_playing=now_playing,
                total_tracks=len(track_uris),
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_music_by_artist",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
                llm_interaction=llm_interaction,
                mopidy_search_results=len(artist_candidates),
            )

            log.info(
                "artist_playback_started", artist=selected_artist.title, tracks=len(track_uris)
            )
            return plan.model_dump()

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_music_by_artist",
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
            tool_name="play_music_by_artist",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def play_playlist(name: str, mode: str = "replace", shuffle: bool = False) -> dict:
    """
    Play a playlist by name.

    Args:
        name: Playlist name
        mode: Playback mode ('replace' or 'enqueue')
        shuffle: Whether to shuffle

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_playlist", name=name)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"name": name, "mode": mode, "shuffle": shuffle}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_playlist",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            # Get all playlists
            log.info("fetching_playlists")
            playlists = await mopidy.get_playlists()

            # Find matching playlists
            name_lower = name.lower()
            matches = []
            for playlist in playlists:
                if name_lower in playlist.get("name", "").lower():
                    matches.append(playlist)

            if not matches:
                error_msg = f"No playlist found matching '{name}'"
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_playlist",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                    mopidy_search_results=0,
                )
                return {"error_code": "not_found", "message": error_msg, "retryable": False}

            # Disambiguate if needed
            llm_interaction = None
            selected_playlist = matches[0]

            if len(matches) > 1:
                log.info("disambiguating_playlists", count=len(matches))
                candidates = [mopidy.playlist_to_candidate(p) for p in matches]
                disambiguator = DisambiguationService()
                ranked, llm_interaction = await disambiguator.disambiguate(
                    query=name, candidates=candidates, context={"search_type": "playlist"}, top_k=1
                )
                if ranked:
                    # Find original playlist
                    for playlist in matches:
                        if playlist.get("uri") == ranked[0].mopidy_uri:
                            selected_playlist = playlist
                            break

            # Get playlist details
            log.info("loading_playlist", uri=selected_playlist.get("uri"))
            playlist_details = await mopidy.get_playlist(selected_playlist["uri"])

            if not playlist_details or not playlist_details.get("tracks"):
                error_msg = f"Playlist '{selected_playlist.get('name')}' is empty"
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_playlist",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                    llm_interaction=llm_interaction,
                    mopidy_search_results=len(matches),
                )
                return {"error_code": "empty_playlist", "message": error_msg, "retryable": False}

            # Extract track URIs
            tracks = playlist_details["tracks"]
            track_uris = [track["uri"] for track in tracks]

            log.info("queuing_playlist_tracks", count=len(track_uris))

            # Queue tracks
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            await mopidy.add_tracks(track_uris)

            if shuffle:
                await mopidy.shuffle_tracklist()

            await mopidy.play()

            # Get now playing
            now_playing = await mopidy.get_now_playing()
            if not now_playing:
                now_playing = NowPlaying(
                    title=tracks[0].get("name", "Unknown"),
                    artist_or_show=tracks[0].get("artists", [{}])[0].get("name"),
                    kind=MediaKind.TRACK,
                )

            # Build result
            plan = PlayPlan(
                playback_url=config.icecast.stream_url,
                now_playing=now_playing,
                total_tracks=len(track_uris),
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_playlist",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
                llm_interaction=llm_interaction,
                mopidy_search_results=len(matches),
            )

            log.info("playlist_playback_started", playlist=selected_playlist.get("name"))
            return plan.model_dump()

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_playlist",
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
            tool_name="play_playlist",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def play_song_search(query: str, mode: str = "replace", limit: int = 10) -> dict:
    """
    Search for and play songs by title/artist keywords.

    Args:
        query: Search query
        mode: Playback mode ('replace' or 'enqueue')
        limit: Maximum number of tracks

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_song_search", query=query)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"query": query, "mode": mode, "limit": limit}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_song_search",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            # Search for tracks
            log.info("searching_tracks")
            results = await mopidy.search(query={"any": [query]})

            # Collect track candidates
            track_candidates: list[MediaCandidate] = []
            for backend_result in results:
                for track in backend_result.get("tracks", []):
                    candidate = mopidy.track_to_candidate(track)
                    track_candidates.append(candidate)

            if not track_candidates:
                error_msg = f"No tracks found matching '{query}'"
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_song_search",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                    mopidy_search_results=0,
                )
                return {"error_code": "not_found", "message": error_msg, "retryable": False}

            log.info("found_tracks", count=len(track_candidates))

            # Disambiguate and rank tracks
            llm_interaction = None
            ranked_tracks = track_candidates[:limit]

            if len(track_candidates) > 1:
                log.info("disambiguating_tracks")
                disambiguator = DisambiguationService()
                ranked, llm_interaction = await disambiguator.disambiguate(
                    query=query,
                    candidates=track_candidates,
                    context={"search_type": "track"},
                    top_k=limit,
                )
                if ranked:
                    ranked_tracks = ranked

            # Get track URIs
            track_uris = [t.mopidy_uri for t in ranked_tracks if t.mopidy_uri]

            if not track_uris:
                error_msg = "No playable tracks found"
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_song_search",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                    llm_interaction=llm_interaction,
                    mopidy_search_results=len(track_candidates),
                )
                return {
                    "error_code": "no_playable_tracks",
                    "message": error_msg,
                    "retryable": False,
                }

            log.info("queuing_tracks", count=len(track_uris))

            # Queue tracks
            if playback_mode == PlaybackMode.REPLACE:
                await mopidy.clear_tracklist()

            await mopidy.add_tracks(track_uris)
            await mopidy.play()

            # Get now playing
            now_playing = await mopidy.get_now_playing()
            if not now_playing:
                first_track = ranked_tracks[0]
                now_playing = NowPlaying(
                    title=first_track.title,
                    artist_or_show=first_track.subtitle,
                    kind=MediaKind.TRACK,
                )

            # Build result
            plan = PlayPlan(
                playback_url=config.icecast.stream_url,
                now_playing=now_playing,
                total_tracks=len(track_uris),
            )

            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_request(
                tool_name="play_song_search",
                input_params=input_params,
                output=plan.model_dump(),
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
                llm_interaction=llm_interaction,
                mopidy_search_results=len(track_candidates),
            )

            log.info("song_search_playback_started", query=query, tracks=len(track_uris))
            return plan.model_dump()

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_song_search",
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
            tool_name="play_song_search",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}


async def play_music_by_genre(
    genre: str, mode: str = "replace", limit: int = 50, shuffle: bool = True
) -> dict:
    """
    Play music by genre.

    Args:
        genre: Genre name
        mode: Playback mode ('replace' or 'enqueue')
        limit: Maximum number of tracks
        shuffle: Whether to shuffle

    Returns:
        PlayPlan dict or error
    """
    start_time = time.time()
    log = logger.bind(tool="play_music_by_genre", genre=genre)
    request_logger = get_request_logger()

    config = get_config()
    input_params = {"genre": genre, "mode": mode, "limit": limit, "shuffle": shuffle}

    try:
        playback_mode = PlaybackMode(mode)
    except ValueError:
        error_msg = f"Invalid mode: {mode}"
        request_logger.log_request(
            tool_name="play_music_by_genre",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=int((time.time() - start_time) * 1000),
            error_message=error_msg,
        )
        return {"error_code": "invalid_mode", "message": error_msg, "retryable": False}

    try:
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            caps = get_capabilities()

            # Strategy 1: Try genre search if supported
            if caps.supports_genre_search():
                log.info("using_genre_search")
                results = await mopidy.search(query={"genre": [genre]})

                tracks = []
                for backend_result in results:
                    tracks.extend(backend_result.get("tracks", []))

                if tracks:
                    tracks = tracks[:limit]
                    track_uris = [track["uri"] for track in tracks]

                    log.info("found_tracks_by_genre", count=len(track_uris))

                    if playback_mode == PlaybackMode.REPLACE:
                        await mopidy.clear_tracklist()

                    await mopidy.add_tracks(track_uris)

                    if shuffle:
                        await mopidy.shuffle_tracklist()

                    await mopidy.play()

                    now_playing = await mopidy.get_now_playing()
                    if not now_playing:
                        now_playing = NowPlaying(
                            title=tracks[0].get("name", "Unknown"),
                            artist_or_show=tracks[0].get("artists", [{}])[0].get("name"),
                            kind=MediaKind.TRACK,
                        )

                    plan = PlayPlan(
                        playback_url=config.icecast.stream_url,
                        now_playing=now_playing,
                        total_tracks=len(track_uris),
                    )

                    latency_ms = int((time.time() - start_time) * 1000)
                    request_logger.log_request(
                        tool_name="play_music_by_genre",
                        input_params=input_params,
                        output=plan.model_dump(),
                        status=RequestStatus.SUCCESS,
                        total_latency_ms=latency_ms,
                        mopidy_search_results=len(tracks),
                    )

                    log.info("genre_playback_started", genre=genre)
                    return plan.model_dump()

            # Strategy 2: Use genre playlist mapping
            log.info("using_genre_playlist_mapping")
            genre_mapping = None
            for mapping in config.genre_mappings:
                if mapping.genre.lower() == genre.lower():
                    genre_mapping = mapping
                    break

            if not genre_mapping or not genre_mapping.playlists:
                error_msg = f"Genre '{genre}' not supported. Configure genre mappings or use a different provider."
                latency_ms = int((time.time() - start_time) * 1000)
                request_logger.log_request(
                    tool_name="play_music_by_genre",
                    input_params=input_params,
                    output={},
                    status=RequestStatus.ERROR,
                    total_latency_ms=latency_ms,
                    error_message=error_msg,
                )
                return {
                    "error_code": "genre_not_configured",
                    "message": error_msg,
                    "retryable": False,
                }

            # Use the first mapped playlist
            playlist_name = genre_mapping.playlists[0]
            log.info("using_genre_playlist", playlist=playlist_name)

            # Delegate to play_playlist
            return await play_playlist(name=playlist_name, mode=mode, shuffle=shuffle)

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("mopidy_error", error=str(e))
        request_logger.log_request(
            tool_name="play_music_by_genre",
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
            tool_name="play_music_by_genre",
            input_params=input_params,
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )
        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}
