# tool_router.py — Security gatekeeper + smart router (MCP + Jira REST)

from tools.mcp_client import call_tool
from tools.jira_adapter import (
    get_issue,
    search_issues,
    get_comments
)

import sys
import json


def execute_tool(tool_name, args):
    """
    Central routing layer for all tool execution.

    Responsibilities:
    1. Enforce tool whitelist (security)
    2. Route to correct backend:
        - MCP (Salesforce)
        - Direct REST (Jira)
    3. Ensure safe execution (no crashes)
    4. Normalize output format (always JSON string)
    """

    # ---------------------------------------------------
    # AUTHORIZED TOOL WHITELIST
    # ---------------------------------------------------
    # Only tools listed here are allowed to execute.
    # Prevents prompt injection / arbitrary tool execution.
    allowed_tools = [
        # 🔹 Salesforce (via MCP)
        "get_support_case",
        "search_cases",
        "list_case_comments",

        # 🔹 Jira (via REST - NEW)
        "jira.get_issue",
        "jira.search",
        "jira.get_comments"
    ]

    # ---------------------------------------------------
    # SECURITY CHECK
    # ---------------------------------------------------
    if tool_name not in allowed_tools:
        error_msg = (
            "Security Violation: "
            f"Unauthorized tool call attempted: {tool_name}"
        )

        sys.stderr.write(f"[Router] {error_msg}\n")
        return "[]"

    try:
        sys.stderr.write(
            f"[Router] Routing tool: {tool_name}\n"
        )

        # ---------------------------------------------------
        # 🔹 JIRA ROUTING (BYPASS MCP)
        # ---------------------------------------------------
        # Jira does NOT go through MCP because:
        # - MCP auth (OAuth) is not usable in backend
        # - REST API is stable and working
        if tool_name == "jira.get_issue":
            result = get_issue(args["issue_key"])

        elif tool_name == "jira.search":
            result = search_issues(args["jql"])

        elif tool_name == "jira.get_comments":
            result = get_comments(args["issue_key"])

        # ---------------------------------------------------
        # 🔹 DEFAULT: MCP ROUTING (Salesforce etc.)
        # ---------------------------------------------------
        else:
            result = call_tool(tool_name, args)

        # ---------------------------------------------------
        # DEFENSIVE RESULT HANDLING
        # ---------------------------------------------------
        # Prevent empty or null responses from breaking LLM flow
        if result is None or result == "":
            sys.stderr.write(
                f"[Router] Warning: {tool_name} returned empty result.\n"
            )
            return "[]"

        # Ensure output is always JSON string
        if not isinstance(result, str):
            return json.dumps(result)

        return result

    except Exception as e:
        # ---------------------------------------------------
        # FAIL-SAFE: NEVER CRASH THE AGENT
        # ---------------------------------------------------
        sys.stderr.write(
            f"[Router] Critical Error executing "
            f"{tool_name}: {str(e)}\n"
        )

        return "[]"
