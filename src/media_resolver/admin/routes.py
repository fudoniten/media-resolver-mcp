"""FastAPI admin UI routes."""

from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_resolver.config import LLMConfig, get_config, reload_config, set_config
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
        provider: str = Form(...),
        model: str = Form(...),
        temperature: float = Form(...),
        max_tokens: int = Form(...),
        base_url: Optional[str] = Form(None),
    ):
        """Update LLM configuration."""
        log = logger.bind(component="admin")

        try:
            config = get_config()

            # Update LLM config
            config.llm.provider = provider
            config.llm.model = model
            config.llm.temperature = temperature
            config.llm.max_tokens = max_tokens
            config.llm.base_url = base_url if base_url else None

            # Apply updated config
            set_config(config)

            log.info("config_updated", provider=provider, model=model)

            return HTMLResponse(
                """
                <div class="alert alert-success">
                    Configuration updated successfully! Changes will take effect for new requests.
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
            ranked, interaction = await service.disambiguate(query, candidates, top_k=len(candidates))

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

        return {
            "status": "running",
            "config": {
                "mopidy_url": config.mopidy.rpc_url,
                "icecast_url": config.icecast.stream_url,
                "llm_provider": config.llm.provider,
                "llm_model": config.llm.model,
            },
            "statistics": stats,
        }

    return app
