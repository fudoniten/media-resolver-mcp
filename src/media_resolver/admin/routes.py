"""FastAPI admin UI routes."""

from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_resolver.config import LLMBackend, get_config, reload_config, set_config
from media_resolver.disambiguation.service import DisambiguationService
from media_resolver.models import MediaCandidate, MediaKind, RequestStatus
from media_resolver.request_logger import get_request_logger

logger = structlog.get_logger()

# Templates directory
ADMIN_DIR = Path(__file__).parent
TEMPLATES_DIR = ADMIN_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_admin_app() -> FastAPI:
    """Create the admin FastAPI application."""
    app = FastAPI(title="Media Resolver Admin")

    @app.get("/", response_class=HTMLResponse)
    async def admin_home(request: Request):
        """Admin dashboard home."""
        config = get_config()
        request_logger = get_request_logger()
        stats = request_logger.get_statistics()

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "config": config,
                "stats": stats,
            },
        )

    @app.get("/config", response_class=HTMLResponse)
    async def config_panel(request: Request):
        """Configuration panel."""
        config = get_config()
        return templates.TemplateResponse(
            "config.html",
            {
                "request": request,
                "config": config,
            },
        )

    @app.post("/config/update")
    async def update_config(
        active_backend: str = Form(...),
    ):
        """Switch active LLM backend."""
        log = logger.bind(component="admin")

        try:
            config = get_config()

            # Check if backend exists
            backend_names = [b.name for b in config.llm.backends]
            if active_backend not in backend_names:
                raise ValueError(
                    f"Backend '{active_backend}' not found. Available: {', '.join(backend_names)}"
                )

            # Update active backend
            config.llm.active_backend = active_backend

            # Apply updated config
            set_config(config)

            log.info("backend_switched", active_backend=active_backend)

            return HTMLResponse(
                f"""
                <div class="alert alert-success">
                    Switched to backend: {active_backend}. Changes will take effect for new requests.
                </div>
                """
            )

        except Exception as e:
            log.error("config_update_failed", error=str(e))
            return HTMLResponse(
                f"""
                <div class="alert alert-error">
                    Failed to update configuration: {str(e)}
                </div>
                """,
                status_code=400,
            )

    @app.get("/test", response_class=HTMLResponse)
    async def test_panel(request: Request):
        """Testing panel."""
        return templates.TemplateResponse("test.html", {"request": request})

    @app.post("/test/disambiguation")
    async def test_disambiguation(
        query: str = Form(...),
        candidates_json: str = Form(...),
    ):
        """Test disambiguation with sample data."""
        log = logger.bind(component="admin_test")

        try:
            import json

            candidates_data = json.loads(candidates_json)

            # Convert to MediaCandidate objects
            candidates = []
            for c in candidates_data:
                candidates.append(
                    MediaCandidate(
                        id=c.get("id", "test"),
                        kind=MediaKind(c.get("kind", "track")),
                        title=c["title"],
                        subtitle=c.get("subtitle"),
                        score=c.get("score", 0.5),
                        snippet=c.get("snippet"),
                    )
                )

            # Run disambiguation
            service = DisambiguationService()
            ranked, interaction = await service.disambiguate(
                query, candidates, top_k=len(candidates)
            )

            result = {
                "ranked_candidates": [c.model_dump() for c in ranked],
                "llm_interaction": interaction.model_dump() if interaction else None,
            }

            return JSONResponse(result)

        except Exception as e:
            log.error("test_disambiguation_failed", error=str(e))
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.get("/requests", response_class=HTMLResponse)
    async def requests_panel(
        request: Request, tool: Optional[str] = None, status: Optional[str] = None, limit: int = 50
    ):
        """Request history panel."""
        request_logger = get_request_logger()

        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = RequestStatus(status)
            except ValueError:
                pass

        # Get filtered requests
        requests = request_logger.get_recent_requests(
            limit=limit, tool_name=tool, status=status_filter
        )

        return templates.TemplateResponse(
            "requests.html",
            {
                "request": request,
                "requests": requests,
                "tool_filter": tool,
                "status_filter": status,
            },
        )

    @app.get("/requests/{request_id}", response_class=HTMLResponse)
    async def request_detail(request: Request, request_id: str):
        """Request detail view."""
        request_logger = get_request_logger()
        req_log = request_logger.get_request(request_id)

        if not req_log:
            raise HTTPException(status_code=404, detail="Request not found")

        return templates.TemplateResponse(
            "request_detail.html",
            {
                "request": request,
                "req_log": req_log,
            },
        )

    @app.get("/status")
    async def status():
        """Server status endpoint."""
        config = get_config()
        request_logger = get_request_logger()
        stats = request_logger.get_statistics()

        active_backend = config.llm.get_active_backend()
        llm_info = {
            "active_backend": config.llm.active_backend,
            "provider": active_backend.provider if active_backend else None,
            "model": active_backend.model if active_backend else None,
            "available_backends": [b.name for b in config.llm.backends],
        }

        return {
            "status": "running",
            "config": {
                "mopidy_url": config.mopidy.rpc_url,
                "icecast_url": config.icecast.stream_url,
                "llm": llm_info,
            },
            "statistics": stats,
        }

    return app
