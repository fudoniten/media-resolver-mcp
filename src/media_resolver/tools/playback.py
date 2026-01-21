"""Playback control MCP tools."""

import time
from typing import Optional

import structlog

from media_resolver.config import get_config
from media_resolver.models import NowPlaying, StreamInfo
from media_resolver.mopidy.client import MopidyClient, MopidyError
from media_resolver.request_logger import RequestStatus, get_request_logger

logger = structlog.get_logger()


async def get_stream_url() -> dict:
    """
    Get the Icecast stream URL that Home Assistant should play.

    Returns:
        Dict with stream URL information
    """
    start_time = time.time()
    log = logger.bind(tool="get_stream_url")
    request_logger = get_request_logger()

    config = get_config()

    try:
        # Return the configured Icecast URL
        result = StreamInfo(
            url=config.icecast.stream_url, mount=config.icecast.mount, status="active"
        )

        latency_ms = int((time.time() - start_time) * 1000)

        request_logger.log_request(
            tool_name="get_stream_url",
            input_params={},
            output=result.model_dump(),
            status=RequestStatus.SUCCESS,
            total_latency_ms=latency_ms,
        )

        log.info("stream_url_returned", url=result.url)
        return result.model_dump()

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("get_stream_url_failed", error=str(e))

        request_logger.log_request(
            tool_name="get_stream_url",
            input_params={},
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )

        return {"error_code": "stream_url_error", "message": str(e), "retryable": False}


async def now_playing() -> dict:
    """
    Get information about currently playing media.

    Returns:
        Dict with now playing information
    """
    start_time = time.time()
    log = logger.bind(tool="now_playing")
    request_logger = get_request_logger()

    config = get_config()

    try:
        async with MopidyClient(config.mopidy.rpc_url, config.mopidy.timeout) as mopidy:
            now_playing_info = await mopidy.get_now_playing()

            if not now_playing_info:
                result = {
                    "playing": False,
                    "message": "Nothing is currently playing",
                }
            else:
                result = {"playing": True, **now_playing_info.model_dump()}

            latency_ms = int((time.time() - start_time) * 1000)

            request_logger.log_request(
                tool_name="now_playing",
                input_params={},
                output=result,
                status=RequestStatus.SUCCESS,
                total_latency_ms=latency_ms,
            )

            log.info("now_playing_returned", playing=result.get("playing"))
            return result

    except MopidyError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("now_playing_failed", error=str(e))

        request_logger.log_request(
            tool_name="now_playing",
            input_params={},
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )

        return {
            "error_code": "mopidy_error",
            "message": f"Failed to get playback status: {e}",
            "retryable": True,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error("now_playing_unexpected_error", error=str(e))

        request_logger.log_request(
            tool_name="now_playing",
            input_params={},
            output={},
            status=RequestStatus.ERROR,
            total_latency_ms=latency_ms,
            error_message=str(e),
        )

        return {"error_code": "unexpected_error", "message": str(e), "retryable": False}
