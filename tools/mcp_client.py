import asyncio
import os
import sys
import traceback
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

# Map each tool to its corresponding MCP server script
SERVER_MAP = {
    "get_account": "mcp_servers/salesforce_server.py",
    "get_opportunities": "mcp_servers/salesforce_server.py",
    "get_support_case": "mcp_servers/salesforce_server.py",
    "search_cases": "mcp_servers/salesforce_server.py",
}

async def run_tool(name, args):
    server_script = SERVER_MAP.get(name)
    
    if not server_script:
        return {"error": f"No MCP server mapped for tool: {name}"}

    # Absolute path check to prevent "File Not Found" errors
    abs_path = os.path.abspath(server_script)
    if not os.path.exists(abs_path):
        return {"error": f"Server script not found at {abs_path}"}

    # Define parameters for the MCP stdio transport
    # Using sys.executable ensures the server runs in the same environment as the client
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[abs_path],
        env=os.environ.copy()
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the MCP session
                await session.initialize()
                
                # Call the specific tool
                result = await session.call_tool(name, args)

                # --- NEW: Check for explicit MCP Error flag ---
                if hasattr(result, 'isError') and result.isError:
                    err_text = result.content[0].text if result.content else "Unknown error"
                    sys.stderr.write(f"--- TOOL ERROR: {name} ---\n{err_text}\n")
                    return {"error": f"Tool execution failed: {err_text}"}

                # CORRECT EXTRACTION: result.content is a LIST of TextContent objects
                if hasattr(result, 'content') and len(result.content) > 0:
                    # Access the first element of the list [0] and get its text
                    return result.content[0].text  
                
                return str(result)

    except Exception as e:
        # LOGGING: Write full traceback to stderr for debugging
        sys.stderr.write(f"--- MCP FATAL SESSION ERROR ---\n{traceback.format_exc()}\n")
        return {"error": f"MCP Session Failed: {str(e)}"}

def call_tool(name, args):
    """
    Wrapper to call async MCP tool from synchronous Flask/Agent code.
    """
    try:
        # Standard execution for synchronous bridge
        return asyncio.run(run_tool(name, args))
    except Exception as e:
        # Catch runtime errors (e.g., if an event loop is already running)
        return {"error": f"Runtime Error: {str(e)}"}
