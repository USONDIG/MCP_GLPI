"""Generic GLPI asset tools.

This module is intentionally independent from the server configuration.  The
server injects its FastMCP instance, GLPI client and dynamic search-field
resolver through register_asset_tools().
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional


READ_ASSET_ITEMTYPES = {
    "Computer",
    "Monitor",
    "NetworkEquipment",
    "Printer",
    "Peripheral",
    "Phone",
    "AllAssets",
}

WRITE_ASSET_ITEMTYPES = READ_ASSET_ITEMTYPES - {"AllAssets"}


def _validate_itemtype(itemtype: str, *, write: bool = False) -> str:
    allowed = WRITE_ASSET_ITEMTYPES if write else READ_ASSET_ITEMTYPES
    if itemtype not in allowed:
        return (
            f"Unsupported asset itemtype '{itemtype}'. "
            f"Allowed values: {', '.join(sorted(allowed))}."
        )
    return ""


def register_asset_tools(
    mcp: Any,
    glpi: Any,
    resolve_search_field_id: Callable[[str, str, str], Awaitable[str]],
) -> Dict[str, Any]:
    """Register generic asset tools on a FastMCP instance.

    A dict of the registered callables is returned so server.py can expose
    them as module globals for direct use and unit testing.
    """

    async def list_assets(
        itemtype: str,
        name_contains: Optional[str] = None,
        range_start: int = 0,
        range_limit: int = 50,
        include_deleted: bool = False,
    ) -> Any:
        """List GLPI assets for a supported itemtype.

        Supported itemtypes: Computer, Monitor, NetworkEquipment, Printer,
        Peripheral, Phone and AllAssets (read-only aggregate).

        name_contains uses GLPI's searchText[name] filter. Pagination is
        controlled by range_start/range_limit.
        """
        error = _validate_itemtype(itemtype)
        if error:
            return {"error": "INVALID_ASSET_ITEMTYPE", "message": error}
        if range_start < 0 or range_limit < 1 or range_limit > 1000:
            return {
                "error": "INVALID_RANGE",
                "message": "range_start must be >= 0 and range_limit must be between 1 and 1000.",
            }

        params: Dict[str, Any] = {
            "range": f"{range_start}-{range_start + range_limit - 1}",
        }
        if name_contains:
            params["searchText[name]"] = name_contains
        if not include_deleted and itemtype != "AllAssets":
            params["searchText[is_deleted]"] = 0
        return await glpi.get(f"/{itemtype}", params=params)

    async def get_asset(itemtype: str, asset_id: int) -> Any:
        """Return one GLPI asset by itemtype and numeric ID."""
        error = _validate_itemtype(itemtype)
        if error:
            return {"error": "INVALID_ASSET_ITEMTYPE", "message": error}
        if itemtype == "AllAssets":
            return {
                "error": "READ_ONLY_AGGREGATE",
                "message": "AllAssets is an aggregate collection; use a concrete itemtype with get_asset.",
            }
        if asset_id < 1:
            return {"error": "INVALID_ASSET_ID", "message": "asset_id must be >= 1."}
        return await glpi.get(f"/{itemtype}/{asset_id}")

    async def search_assets(
        itemtype: str,
        query: str,
        range_start: int = 0,
        range_limit: int = 50,
    ) -> Any:
        """Search assets by name using GLPI's /search/{itemtype} endpoint.

        The numeric search field ID is discovered dynamically with
        listSearchOptions so this remains compatible with GLPI 10/11.
        """
        error = _validate_itemtype(itemtype)
        if error:
            return {"error": "INVALID_ASSET_ITEMTYPE", "message": error}
        if not query.strip():
            return {"error": "EMPTY_QUERY", "message": "query must not be empty."}
        if range_start < 0 or range_limit < 1 or range_limit > 1000:
            return {
                "error": "INVALID_RANGE",
                "message": "range_start must be >= 0 and range_limit must be between 1 and 1000.",
            }

        name_field = await resolve_search_field_id(itemtype, "name", "1")
        params: Dict[str, Any] = {
            "criteria[0][field]": name_field,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": query,
            "range": f"{range_start}-{range_start + range_limit - 1}",
        }
        return await glpi.get(f"/search/{itemtype}", params=params)

    async def create_asset(itemtype: str, fields: Dict[str, Any]) -> Any:
        """Create an asset with raw GLPI fields.

        Only concrete hardware itemtypes are writable. Do not invent foreign
        key IDs (locations_id, states_id, manufacturers_id, users_id, etc.).
        """
        error = _validate_itemtype(itemtype, write=True)
        if error:
            return {"error": "INVALID_ASSET_ITEMTYPE", "message": error}
        if not fields:
            return {"error": "EMPTY_FIELDS", "message": "fields must contain at least one GLPI field."}
        if "id" in fields:
            return {"error": "IMMUTABLE_FIELD", "message": "Do not provide id when creating an asset."}
        return await glpi.post(f"/{itemtype}", {"input": fields})

    async def update_asset(itemtype: str, asset_id: int, fields: Dict[str, Any]) -> Any:
        """Update only the supplied fields of an existing asset."""
        error = _validate_itemtype(itemtype, write=True)
        if error:
            return {"error": "INVALID_ASSET_ITEMTYPE", "message": error}
        if asset_id < 1:
            return {"error": "INVALID_ASSET_ID", "message": "asset_id must be >= 1."}
        if not fields:
            return {"error": "EMPTY_FIELDS", "message": "fields must contain at least one changed field."}
        if "id" in fields and fields["id"] != asset_id:
            return {
                "error": "ASSET_ID_MISMATCH",
                "message": "fields.id must be omitted or match asset_id.",
            }
        payload = dict(fields)
        payload.pop("id", None)
        return await glpi.put(f"/{itemtype}/{asset_id}", {"input": payload})

    async def delete_asset(itemtype: str, asset_id: int, purge: bool = False) -> Any:
        """Delete an asset.

        purge=False is the safe default and moves trash-capable assets to the
        GLPI trash. purge=True sends force_purge=true and is permanent.
        """
        error = _validate_itemtype(itemtype, write=True)
        if error:
            return {"error": "INVALID_ASSET_ITEMTYPE", "message": error}
        if asset_id < 1:
            return {"error": "INVALID_ASSET_ID", "message": "asset_id must be >= 1."}
        params = {"force_purge": "true"} if purge else None
        return await glpi.delete(f"/{itemtype}/{asset_id}", params=params)

    tools = {
        "list_assets": list_assets,
        "get_asset": get_asset,
        "search_assets": search_assets,
        "create_asset": create_asset,
        "update_asset": update_asset,
        "delete_asset": delete_asset,
    }
    for func in tools.values():
        mcp.tool()(func)
    return tools
