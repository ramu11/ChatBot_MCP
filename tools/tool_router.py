# tool_router.py — The security gatekeeper for MCP tool execution
from tools.mcp_client import call_tool
import sys
import json

def execute_tool(tool_name, args):
    """
    Acts as a secure router for MCP tools. 
    Enforces a whitelist and ensures failures don't crash the agent's logic.
    """
    
    # AUTHORIZED TOOL WHITELIST
    allowed_tools = [
        "get_support_case",    # Main Case Header
        "search_cases",        # SBR/Status Filtering
        "get_account",         # Account/Customer Details
        "get_opportunities",   # Sales/Opportunity context
        "list_case_comments",  # Authorized for Deep Scan (Technical Notes)
        "get_external_updates",# Authorized for Deep Scan (Jira/Bugzilla Trackers)
        "get_jira_details"     # NEW: Direct Engineering Access (Real-time Status/Comments)
    ]

    # 1. Security Check
    if tool_name not in allowed_tools:
        error_msg = f"Security Violation: Unauthorized tool call attempted: {tool_name}"
        sys.stderr.write(f"[Router] {error_msg}\n")
        # Return empty list string to prevent agent.py from breaking during iteration
        return "[]"

    # 2. Execution Bridge
    try:
        sys.stderr.write(f"[Router] Calling authorized tool: {tool_name}\n")
        
        # Pass the request to the MCP Client (stdio/SSE bridge)
        result = call_tool(tool_name, args)
        
        # 3. Defensive Result Handling
        if result is None or result == "":
            sys.stderr.write(f"[Router] Warning: {tool_name} returned empty result.\n")
            return "[]"
            
        # Ensure the result is a string (JSON) for the agent to parse
        if not isinstance(result, str):
            return json.dumps(result)
            
        return result

    except Exception as e:
        sys.stderr.write(f"[Router] Critical Error executing {tool_name}: {str(e)}\n")
        # Return a valid JSON empty list string so agent.py remains stable
        return "[]"
