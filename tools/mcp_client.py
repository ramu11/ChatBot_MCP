# tools/mcp_client.py
"""
Model Context Protocol (MCP) Stdio Client for Local Server Execution.

This module provides the low-level communication bridge to execute local MCP server scripts
via stdio streams (primarily for Salesforce tools). It handles server process spawning,
`ClientSession` initialization, content extraction, tool schema caching, and synchronous
loop wrapping for integration with synchronous agent components.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, Union

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# ---------------------------------------------------------
# LOCAL MCP SERVER MAPPING (Salesforce Backend)
# ---------------------------------------------------------
# Maps tool name identifiers to relative python script paths for MCP servers
SERVER_MAP = {
    "get_support_case": "mcp_servers/salesforce_server.py",
    "search_cases": "mcp_servers/salesforce_server.py",
    "search_historical_cases": "mcp_servers/salesforce_server.py",
    "list_case_comments": "mcp_servers/salesforce_server.py",
    "get_external_updates": "mcp_servers/salesforce_server.py",
}

# ---------------------------------------------------------
# TOOL SCHEMA CACHE
# ---------------------------------------------------------
# Caches ListToolsRequest schema responses per script path to prevent repeated round-trips
_TOOL_SCHEMA_CACHE: Dict[str, Any] = {}


# ---------------------------------------------------------
# HELPER: SAFE CONTENT EXTRACTION
# ---------------------------------------------------------
def extract_mcp_content(result: Any) -> str:
    """
    Extracts text payload or JSON content safely from MCP `CallToolResult` objects.

    Inspects content structures across various response types (FastMCP `TextContent`,
    dictionaries, or primitive types) and returns a normalized string.

    Args:
        result (Any): The raw result object returned by `ClientSession.call_tool()`.

    Returns:
        str: Extracted raw text or JSON string, or `"[]"` on empty content.
    """
    try:
        if hasattr(result, "content") and len(result.content) > 0:
            content_item = result.content[0]

            # FastMCP TextContent object format check
            if hasattr(content_item, "text"):
                return content_item.text

            # Standard dictionary payload check
            if isinstance(content_item, dict):
                return content_item.get("text", "[]")

            return str(content_item)

        return "[]"

    except Exception as e:
        return json.dumps({"error": f"Content extraction failed: {str(e)}"})


# ---------------------------------------------------------
# ASYNC TOOL SCHEMA CACHER
# ---------------------------------------------------------
async def get_cached_tool_schemas(server_script_key: str = "get_support_case") -> Any:
    """
    Fetches and caches the tool schema listing (`ListToolsRequest`) from an MCP server script.

    If cached schemas exist for the specified server, returns them immediately to prevent
    unnecessary stdio process spawning and network round-trips.

    Args:
        server_script_key (str): A tool key mapped in SERVER_MAP to identify the target server script.

    Returns:
        Any: The cached tool listing response object, or an error payload dict.
    """
    script_rel_path = SERVER_MAP.get(server_script_key)

    if not script_rel_path:
        return {"error": f"No server mapping for {server_script_key}"}

    # Check cache hit
    if script_rel_path in _TOOL_SCHEMA_CACHE:
        sys.stderr.write(
            f"[MCP Client] Returning cached schemas for {script_rel_path}\n"
        )
        return _TOOL_SCHEMA_CACHE[script_rel_path]

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_script_path = os.path.join(base_dir, script_rel_path)

    if not os.path.exists(abs_script_path):
        return {"error": f"Server script not found at {abs_script_path}"}

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[abs_script_path],
        env=os.environ.copy(),
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Fetch and store tool listing in cache
                tools_result = await session.list_tools()
                _TOOL_SCHEMA_CACHE[script_rel_path] = tools_result
                sys.stderr.write(
                    f"[MCP Client] Cached tool schemas for {script_rel_path}\n"
                )
                return tools_result

    except Exception as e:
        sys.stderr.write(f"\n[MCP Client] Failed to fetch tool schemas: {str(e)}\n")
        return {"error": f"Failed to fetch tool schemas: {str(e)}"}


def get_tool_schemas(server_script_key: str = "get_support_case") -> Any:
    """
    Synchronous wrapper to retrieve and cache tool schemas for orchestrators / agent initialization.
    """
    try:
        return asyncio.run(get_cached_tool_schemas(server_script_key))
    except Exception as e:
        sys.stderr.write(f"\n[MCP Client] Schema retrieval error: {str(e)}\n")
        return {"error": f"Schema retrieval error: {str(e)}"}


# ---------------------------------------------------------
# ASYNC EXECUTOR: LOCAL MCP SERVERS
# ---------------------------------------------------------
async def run_local_tool(name: str, args: Dict[str, Any]) -> str:
    """
    Spawns a local MCP server process via stdio and executes a tool command asynchronously.

    Resolves server script paths, configures python subprocess environment variables,
    initializes the stdio MCP `ClientSession`, and performs error-checked tool invocation.

    Args:
        name (str): The MCP tool name to execute.
        args (Dict[str, Any]): Dictionary of tool arguments.

    Returns:
        str: Extracted tool text response or JSON error object string.
    """
    script_rel_path = SERVER_MAP.get(name)

    if not script_rel_path:
        return json.dumps({"error": f"No server mapping for {name}"})

    # Resolve absolute script path relative to the root project directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_script_path = os.path.join(base_dir, script_rel_path)

    if not os.path.exists(abs_script_path):
        return json.dumps({"error": f"Server script not found at {abs_script_path}"})

    # Build server process spawn arguments using current python executable environment
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[abs_script_path],
        env=os.environ.copy(),
    )

    try:
        # Establish stdio stream transport to local server script process
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Perform async MCP tool invocation
                result = await session.call_tool(name, args)

                # Check for explicit MCP server execution errors
                if hasattr(result, "isError") and result.isError:
                    error_detail = (
                        str(result.content)
                        if hasattr(result, "content")
                        else "Unknown tool error"
                    )
                    return json.dumps(
                        {"error": "MCP Tool Error", "details": error_detail}
                    )

                return extract_mcp_content(result)

    except Exception as e:
        sys.stderr.write(f"\n[MCP Client] Connection Failed: {str(e)}\n")
        return json.dumps({"error": f"MCP Connection Failed: {str(e)}"})


# ---------------------------------------------------------
# INTERNAL ROUTER
# ---------------------------------------------------------
async def run_tool(name: str, args: Dict[str, Any]) -> str:
    """
    Internal asynchronous routing entry point for local MCP tools.

    Args:
        name (str): Tool identifier string.
        args (Dict[str, Any]): Tool argument map.

    Returns:
        str: Output result from local tool execution.
    """
    return await run_local_tool(name, args)


# ---------------------------------------------------------
# SYNCHRONOUS WRAPPER
# ---------------------------------------------------------
def call_tool(name: str, args: Dict[str, Any]) -> str:
    """
    Synchronous wrapper used by orchestrators to execute async MCP commands.

    Manages event loop execution via `asyncio.run()`, catching and formatting
    runtime exception states gracefully.

    Args:
        name (str): Tool identifier string.
        args (Dict[str, Any]): Tool argument map.

    Returns:
        str: JSON-formatted text result from tool execution.
    """
    try:
        return asyncio.run(run_tool(name, args))

    except Exception as e:
        sys.stderr.write(f"\n[MCP Client] Runtime Error: {str(e)}\n")
        return json.dumps({"error": f"Runtime Error: {str(e)}"})
