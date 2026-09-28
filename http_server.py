"""Authenticated, stateless Streamable HTTP entry point for Render."""

import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

# Public hosting must verify GLPI's certificate by default.
os.environ.setdefault("GLPI_VERIFY_TLS", "true")
if Path(__file__).with_name("config.json").exists():
    raise RuntimeError("HTTP deployment uses environment variables; remove config.json")

from server import mcp  # noqa: E402


def configuration_ready():
    """Fail closed while secrets are being entered in the Render dashboard."""
    token = os.environ.get("MCP_AUTH_TOKEN", "")
    url = urlsplit(os.environ.get("GLPI_URL", ""))
    return (
        len(token) >= 32
        and url.scheme == "https"
        and bool(url.hostname)
        and not url.username
        and not url.password
        and bool(os.environ.get("GLPI_APP_TOKEN", ""))
        and bool(os.environ.get("GLPI_USER_TOKEN", ""))
        and os.environ.get("GLPI_VERSION", "10") in ("10", "11")
    )


@mcp.custom_route("/healthz", methods=["GET"])
async def health(request: Request):
    # Liveness only: never query GLPI or return configuration/secrets here.
    return JSONResponse({"status": "ok"})


class BearerAuth:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/healthz":
            return await self.app(scope, receive, send)
        expected = os.environ.get("MCP_AUTH_TOKEN", "")
        if len(expected) < 32:
            response = JSONResponse({"error": "Service not configured"}, status_code=503)
        else:
            request = Request(scope)
            scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not secrets.compare_digest(
                supplied.encode(), expected.encode()
            ):
                response = JSONResponse(
                    {"error": "Unauthorized"}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
                )
            elif not configuration_ready():
                response = JSONResponse({"error": "Service not configured"}, status_code=503)
            else:
                return await self.app(scope, receive, send)
        await response(scope, receive, send)


def create_app():
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    origins = ["http://localhost:*", "http://127.0.0.1:*"]
    render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if render_host:
        hosts.extend([render_host, f"{render_host}:443"])
        origins.append(f"https://{render_host}")
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth)
    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
