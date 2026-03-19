from tools.mcp_client import call_tool

def execute_tool(tool_name, args):
    allowed_tools = ["get_support_case", "search_cases", "get_account", "get_opportunities"]

    if tool_name in allowed_tools:
        print(f"[Router] Calling {tool_name} with: {args}")
        return call_tool(tool_name, args)

    raise Exception(f"Unauthorized tool: {tool_name}")

