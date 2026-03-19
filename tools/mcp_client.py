import asyncio
import os
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
    server_params = StdioServerParameters(
        command="python",
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

                # CORRECT EXTRACTION: result.content is a LIST of TextContent objects
                if hasattr(result, 'content') and len(result.content) > 0:
                    # Access the first element of the list [0] and get its text
                    return result.content[0].text  
                
                # Fallback for structured content if text content is missing
                if hasattr(result, 'isError') and result.isError:
                    return {"error": "Tool execution failed on server"}

                return str(result)

    except Exception as e:
        return {"error": f"MCP Session Failed: {str(e)}"}

def call_tool(name, args):
    """
    Wrapper to call async MCP tool from synchronous Flask/Agent code.
    """
    try:
        return asyncio.run(run_tool(name, args))
    except Exception as e:
        return {"error": f"Runtime Error: {str(e)}"}

