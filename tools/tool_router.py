from tools.mcp_client import call_tool

def execute_tool(tool_name, args):
    """Acts as a router for MCP tools. Includes permissions for deep-scan tools."""
    allowed_tools = [
        "get_support_case", 
        "search_cases", 
        "get_account", 
        "get_opportunities",
        "list_case_comments",  # Authorized for deep scan
        "get_external_updates" # Authorized for deep scan
    ]

    if tool_name in allowed_tools:
        print(f"[Router] Calling authorized tool: {tool_name}")
        return call_tool(tool_name, args)

    raise Exception(f"Security: Unauthorized tool call attempted: {tool_name}")
