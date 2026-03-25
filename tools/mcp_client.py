# mcp_client.py — The Bridge between Synchronous Agent and Asynchronous MCP Servers
import asyncio
import os
import sys
import json
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

# Mapping Project Tools to their specific MCP Server scripts
SERVER_MAP = {
    "get_account": "mcp_servers/salesforce_server.py",
    "get_support_case": "mcp_servers/salesforce_server.py",
    "search_cases": "mcp_servers/salesforce_server.py",
    "list_case_comments": "mcp_servers/salesforce_server.py",
    "get_external_updates": "mcp_servers/salesforce_server.py",
    "get_opportunities": "mcp_servers/salesforce_server.py",
    "get_jira_details": "mcp_servers/salesforce_server.py" # Mapping the new Jira Tool
}

async def run_tool(name, args):
    script_rel_path = SERVER_MAP.get(name)
    if not script_rel_path:
        return json.dumps({"error": f"No server mapping for {name}"})
    
    # Resolve project root path
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_script_path = os.path.join(base_dir, script_rel_path)
    
    if not os.path.exists(abs_script_path):
        return json.dumps({"error": f"Server script not found at {abs_script_path}"})

    # Prepare stdio parameters to spawn the server process
    server_params = StdioServerParameters(
        command=sys.executable, 
        args=[abs_script_path], 
        env=os.environ.copy()
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Perform the tool call
                result = await session.call_tool(name, args)
                
                # 1. Handle explicit MCP errors (e.g. tool execution failed inside the server)
                if hasattr(result, 'isError') and result.isError:
                    error_detail = str(result.content) if hasattr(result, 'content') else "Unknown tool error"
                    return json.dumps({"error": "MCP Tool Error", "details": error_detail})

                # 2. Content Extraction Logic
                if hasattr(result, 'content') and len(result.content) > 0:
                    content_item = result.content[0]
                    
                    # Case A: Standard TextContent object (Common for FastMCP)
                    if hasattr(content_item, 'text'):
                        return content_item.text
                    
                    # Case B: Content item is a raw dictionary
                    if isinstance(content_item, dict):
                        return content_item.get("text", "[]")
                    
                    # Case C: Fallback to string representation
                    return str(content_item)
                
                return "[]"
                
    except Exception as e:
        sys.stderr.write(f"[MCP Client] Connection Failed: {str(e)}\n")
        return json.dumps({"error": f"MCP Connection Failed: {str(e)}"})

def call_tool(name, args):
    """Synchronous wrapper for agent.py logic."""
    try:
        # Runs the async loop for the tool call and returns the JSON string
        return asyncio.run(run_tool(name, args))
    except Exception as e:
        sys.stderr.write(f"[MCP Client] Runtime Error: {str(e)}\n")
        return json.dumps({"error": f"Runtime Error: {str(e)}"})
