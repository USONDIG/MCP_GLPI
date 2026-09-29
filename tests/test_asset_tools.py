"""Tests for the generic GLPI asset tools."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("GLPI_URL", "https://glpi.test.local")
os.environ.setdefault("GLPI_APP_TOKEN", "app-token-test")
os.environ.setdefault("GLPI_USER_TOKEN", "user-token-test")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

import server  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_session():
    server._session_token = "stub-session-token"
    server._search_options_cache.clear()
    yield
    server._session_token = None
    server._search_options_cache.clear()


def _params_of(call) -> dict:
    return dict(httpx.URL(str(call.request.url)).params.multi_items())


def _input_of(call) -> dict:
    return json.loads(call.request.content)["input"]


@pytest.mark.asyncio
@respx.mock
async def test_list_assets_computers_with_filters_and_pagination():
    route = respx.get(f"{server.GLPI_URL}{server._API_PREFIX}/Computer").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "PC-001"}])
    )
    result = await server.list_assets("Computer", "PC-", range_start=10, range_limit=25)
    assert route.called
    params = _params_of(respx.calls.last)
    assert params["range"] == "10-34"
    assert params["searchText[name]"] == "PC-"
    assert params["searchText[is_deleted]"] == "0"
    assert result[0]["name"] == "PC-001"


@pytest.mark.asyncio
@respx.mock
async def test_get_asset_uses_concrete_itemtype_and_id():
    route = respx.get(f"{server.GLPI_URL}{server._API_PREFIX}/Printer/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "PRN-42"})
    )
    result = await server.get_asset("Printer", 42)
    assert route.called
    assert result["id"] == 42


@pytest.mark.asyncio
@respx.mock
async def test_search_assets_discovers_name_field_dynamically():
    respx.get(f"{server.GLPI_URL}{server._API_PREFIX}/listSearchOptions/NetworkEquipment").mock(
        return_value=httpx.Response(
            200,
            json={"99": {"field": "name", "table": "glpi_networkequipments"}},
        )
    )
    route = respx.get(
        f"{server.GLPI_URL}{server._API_PREFIX}/search/NetworkEquipment"
    ).mock(return_value=httpx.Response(200, json={"data": []}))

    await server.search_assets("NetworkEquipment", "switch")
    params = _params_of(route.calls.last)
    assert params["criteria[0][field]"] == "99"
    assert params["criteria[0][searchtype]"] == "contains"
    assert params["criteria[0][value]"] == "switch"


@pytest.mark.asyncio
@respx.mock
async def test_create_asset_wraps_fields_in_input():
    route = respx.post(f"{server.GLPI_URL}{server._API_PREFIX}/Computer").mock(
        return_value=httpx.Response(201, json={"id": 7})
    )
    result = await server.create_asset(
        "Computer", {"name": "PC-007", "serial": "ABC123"}
    )
    assert route.called
    assert _input_of(route.calls.last) == {"name": "PC-007", "serial": "ABC123"}
    assert result["id"] == 7


@pytest.mark.asyncio
@respx.mock
async def test_update_asset_only_sends_changed_fields():
    route = respx.put(f"{server.GLPI_URL}{server._API_PREFIX}/Monitor/8").mock(
        return_value=httpx.Response(200, json=[{"8": True}])
    )
    await server.update_asset("Monitor", 8, {"name": "Screen-08"})
    assert route.called
    assert _input_of(route.calls.last) == {"name": "Screen-08"}


@pytest.mark.asyncio
@respx.mock
async def test_delete_asset_defaults_to_trash():
    route = respx.delete(f"{server.GLPI_URL}{server._API_PREFIX}/Phone/9").mock(
        return_value=httpx.Response(200, json=[{"9": True}])
    )
    await server.delete_asset("Phone", 9)
    assert route.called
    assert "force_purge" not in _params_of(route.calls.last)


@pytest.mark.asyncio
@respx.mock
async def test_delete_asset_purge_is_explicit():
    route = respx.delete(f"{server.GLPI_URL}{server._API_PREFIX}/Peripheral/9").mock(
        return_value=httpx.Response(200, json=[{"9": True}])
    )
    await server.delete_asset("Peripheral", 9, purge=True)
    assert _params_of(route.calls.last)["force_purge"] == "true"


@pytest.mark.asyncio
async def test_allassets_is_read_only():
    result = await server.create_asset("AllAssets", {"name": "nope"})
    assert result["error"] == "INVALID_ASSET_ITEMTYPE"


@pytest.mark.asyncio
async def test_unknown_itemtype_is_rejected():
    result = await server.list_assets("Software")
    assert result["error"] == "INVALID_ASSET_ITEMTYPE"


@pytest.mark.asyncio
async def test_asset_tools_are_registered():
    names = {tool.name for tool in await server.mcp.list_tools()}
    for expected in (
        "list_assets",
        "get_asset",
        "search_assets",
        "create_asset",
        "update_asset",
        "delete_asset",
    ):
        assert expected in names
