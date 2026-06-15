# mcp_client.py — MCP client for LOCAL servers only (Salesforce)

import asyncio
import os
import sys
import json

from mcp.client.stdio import (
    stdio_client,
    StdioServerParameters
)

from mcp import ClientSession


# ---------------------------------------------------------
# LOCAL MCP SERVER MAP (Salesforce Tools)
# ---------------------------------------------------------
SERVER_MAP = {
    "get_support_case": "mcp_servers/salesforce_server.py",
    "search_cases": "mcp_servers/salesforce_server.py",
    "list_case_comments": "mcp_servers/salesforce_server.py",
    "get_external_updates": "mcp_servers/salesforce_server.py"
}


# ---------------------------------------------------------
# SAFE CONTENT EXTRACTION
# ---------------------------------------------------------
def extract_mcp_content(result):
    """
    Extracts usable text/JSON from MCP response safely.
    """

    try:
        if hasattr(result, "content") and len(result.content) > 0:

            content_item = result.content[0]

            # FastMCP TextContent
            if hasattr(content_item, "text"):
                return content_item.text

            # Dict response
            if isinstance(content_item, dict):
                return content_item.get("text", "[]")

            return str(content_item)

        return "[]"

    except Exception as e:
        return json.dumps({
            "error": f"Content extraction failed: {str(e)}"
        })


# ---------------------------------------------------------
# LOCAL MCP FLOW (Salesforce)
# ---------------------------------------------------------
async def run_local_tool(name, args):
    """
    Executes a tool against a local MCP server (Salesforce).
    """

    script_rel_path = SERVER_MAP.get(name)

    if not script_rel_path:
        return json.dumps({
            "error": f"No server mapping for {name}"
        })

    # Resolve absolute path
    base_dir = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    abs_script_path = os.path.join(
        base_dir,
        script_rel_path
    )

    if not os.path.exists(abs_script_path):
        return json.dumps({
            "error": f"Server script not found at {abs_script_path}"
        })

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[abs_script_path],
        env=os.environ.copy()
    )

    try:
        async with stdio_client(server_params) as (read, write):

            async with ClientSession(read, write) as session:

                await session.initialize()

                result = await session.call_tool(
                    name,
                    args
                )

                # Handle MCP error explicitly
                if hasattr(result, "isError") and result.isError:

                    error_detail = (
                        str(result.content)
                        if hasattr(result, "content")
                        else "Unknown tool error"
                    )

                    return json.dumps({
                        "error": "MCP Tool Error",
                        "details": error_detail
                    })

                return extract_mcp_content(result)

    except Exception as e:
        sys.stderr.write(
            f"\n[MCP Client] Connection Failed: {str(e)}\n"
        )

        return json.dumps({
            "error": f"MCP Connection Failed: {str(e)}"
        })


# ---------------------------------------------------------
# ROUTER (LOCAL ONLY)
# ---------------------------------------------------------
async def run_tool(name, args):
    """
    Routes to LOCAL MCP only.
    Jira is handled outside (tool_router → jira_adapter).
    """
    return await run_local_tool(name, args)


# ---------------------------------------------------------
# SYNC WRAPPER
# ---------------------------------------------------------
def call_tool(name, args):
    """
    Synchronous wrapper used by agent.
    """

    try:
        return asyncio.run(run_tool(name, args))

    except Exception as e:
        sys.stderr.write(
            f"\n[MCP Client] Runtime Error: {str(e)}\n"
        )

        return json.dumps({
            "error": f"Runtime Error: {str(e)}"
        })
