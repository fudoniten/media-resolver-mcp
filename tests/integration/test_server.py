"""Integration tests for Media Resolver MCP server."""

import pytest
from fastapi.testclient import TestClient

from media_resolver.server import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint returns service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "endpoints" in data


def test_admin_status(client):
    """Test admin status endpoint."""
    response = client.get("/admin/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "config" in data
    assert "statistics" in data


def test_admin_dashboard(client):
    """Test admin dashboard loads."""
    response = client.get("/admin/")
    assert response.status_code == 200
    assert b"Media Resolver" in response.content


def test_admin_config_page(client):
    """Test admin config page loads."""
    response = client.get("/admin/config")
    assert response.status_code == 200
    assert b"Configuration" in response.content


def test_admin_requests_page(client):
    """Test admin requests page loads."""
    response = client.get("/admin/requests")
    assert response.status_code == 200
    assert b"Request History" in response.content
