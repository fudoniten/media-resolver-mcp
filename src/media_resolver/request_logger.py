"""Request logging infrastructure for tracking MCP tool calls."""

import uuid
from collections import deque
from datetime import datetime
from typing import Any

import structlog

from media_resolver.config import get_config
from media_resolver.models import LLMInteraction, RequestLog, RequestStatus

logger = structlog.get_logger()


class RequestLogger:
    """
    In-memory request logger with circular buffer.

    Tracks all MCP tool invocations with their inputs, outputs, and LLM interactions.
    """

    def __init__(self, max_size: int | None = None):
        """
        Initialize request logger.

        Args:
            max_size: Maximum number of requests to keep. If None, uses config.
        """
        if max_size is None:
            config = get_config()
            max_size = config.max_request_history

        self._logs: deque[RequestLog] = deque(maxlen=max_size)
        self.log = logger.bind(component="request_logger")
        self.log.info("request_logger_initialized", max_size=max_size)

    def log_request(
        self,
        tool_name: str,
        input_params: dict[str, Any],
        output: dict[str, Any],
        status: RequestStatus,
        total_latency_ms: int,
        llm_interaction: LLMInteraction | None = None,
        error_message: str | None = None,
        mopidy_search_results: int | None = None,
    ) -> str:
        """
        Log a request.

        Args:
            tool_name: Name of the MCP tool
            input_params: Input parameters
            output: Output data
            status: Request status
            total_latency_ms: Total latency in milliseconds
            llm_interaction: Optional LLM interaction details
            error_message: Optional error message
            mopidy_search_results: Number of Mopidy search results

        Returns:
            Request ID
        """
        request_id = f"req_{uuid.uuid4().hex[:12]}"

        request_log = RequestLog(
            timestamp=datetime.now(),
            request_id=request_id,
            tool_name=tool_name,
            input_params=input_params,
            llm_interaction=llm_interaction,
            output=output,
            status=status,
            error_message=error_message,
            total_latency_ms=total_latency_ms,
            mopidy_search_results=mopidy_search_results,
            disambiguation_occurred=llm_interaction is not None,
        )

        self._logs.append(request_log)

        self.log.info(
            "request_logged",
            request_id=request_id,
            tool_name=tool_name,
            status=status.value,
            latency_ms=total_latency_ms,
        )

        return request_id

    def get_recent_requests(
        self,
        limit: int | None = None,
        tool_name: str | None = None,
        status: RequestStatus | None = None,
    ) -> list[RequestLog]:
        """
        Get recent requests with optional filtering.

        Args:
            limit: Maximum number of requests to return
            tool_name: Filter by tool name
            status: Filter by status

        Returns:
            List of request logs (newest first)
        """
        # Convert deque to list (newest last in deque)
        all_logs = list(self._logs)

        # Filter
        filtered = all_logs
        if tool_name:
            filtered = [log for log in filtered if log.tool_name == tool_name]
        if status:
            filtered = [log for log in filtered if log.status == status]

        # Reverse to get newest first
        filtered.reverse()

        # Limit
        if limit:
            filtered = filtered[:limit]

        return filtered

    def get_request(self, request_id: str) -> RequestLog | None:
        """
        Get a specific request by ID.

        Args:
            request_id: Request ID

        Returns:
            RequestLog or None if not found
        """
        for log in self._logs:
            if log.request_id == request_id:
                return log
        return None

    def get_statistics(self) -> dict[str, Any]:
        """
        Get statistics about logged requests.

        Returns:
            Dict with statistics
        """
        if not self._logs:
            return {
                "total_requests": 0,
                "by_tool": {},
                "by_status": {},
                "avg_latency_ms": 0,
                "disambiguations": 0,
            }

        total = len(self._logs)

        # Count by tool
        by_tool: dict[str, int] = {}
        for log in self._logs:
            by_tool[log.tool_name] = by_tool.get(log.tool_name, 0) + 1

        # Count by status
        by_status: dict[str, int] = {}
        for log in self._logs:
            by_status[log.status.value] = by_status.get(log.status.value, 0) + 1

        # Average latency
        total_latency = sum(log.total_latency_ms for log in self._logs)
        avg_latency = total_latency // total if total > 0 else 0

        # Disambiguations
        disambiguations = sum(1 for log in self._logs if log.disambiguation_occurred)

        return {
            "total_requests": total,
            "by_tool": by_tool,
            "by_status": by_status,
            "avg_latency_ms": avg_latency,
            "disambiguations": disambiguations,
        }

    def clear(self) -> None:
        """Clear all logged requests."""
        self._logs.clear()
        self.log.info("request_history_cleared")


# Global logger instance
_request_logger: RequestLogger | None = None


def get_request_logger() -> RequestLogger:
    """Get the global request logger instance."""
    global _request_logger
    if _request_logger is None:
        _request_logger = RequestLogger()
    return _request_logger


def set_request_logger(logger: RequestLogger) -> None:
    """Set the global request logger instance (useful for testing)."""
    global _request_logger
    _request_logger = logger
