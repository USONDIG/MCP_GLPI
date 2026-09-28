"""HTTP transport tests. All credentials here are isolated test fixtures."""
import secrets

import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import http_server
    # Build one transport per server instance (as in production).
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("RENDER_EXTERNAL_HOSTNAME", "glpi-test.onrender.com")
        with TestClient(http_server.create_app(), base_url="https://glpi-test.onrender.com") as c:
            yield c


@pytest.fixture
def configured(monkeypatch):
    token = secrets.token_urlsafe(48)
    monkeypatch.setenv("MCP_AUTH_TOKEN", token)
    monkeypatch.setenv("GLPI_URL", "https://glpi.test.local")
    monkeypatch.setenv("GLPI_APP_TOKEN", "test-only-app")
    monkeypatch.setenv("GLPI_USER_TOKEN", "test-only-user")
    monkeypatch.setenv("GLPI_VERSION", "10")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"}


def test_health_without_secrets_and_closed_mcp(client, monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.post("/mcp", json={}).status_code == 503


def test_reject_missing_wrong_and_malformed_token(client, configured):
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}):
        response = client.post("/mcp", headers=headers, json={})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_missing_glpi_secret_fails_closed(client, configured, monkeypatch):
    monkeypatch.delenv("GLPI_USER_TOKEN")
    assert client.post("/mcp", headers=configured, json={}).status_code == 503


def test_reject_bad_host_and_origin(client, configured):
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post("/mcp", headers={**configured, "Host": "evil.example"}, json=request).status_code == 421
    assert client.post("/mcp", headers={**configured, "Origin": "https://evil.example"}, json=request).status_code == 403


def test_initialize_and_list_tools_stateless(client, configured):
    response = client.post("/mcp", headers=configured, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "transport-test", "version": "1"}},
    })
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "GLPI MCP"
    assert "mcp-session-id" not in response.headers
    response = client.post("/mcp", headers=configured, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/list",
    })
    assert response.status_code == 200
    assert any(t["name"] == "list_tickets" for t in response.json()["result"]["tools"])
