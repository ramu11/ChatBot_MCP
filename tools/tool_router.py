# tools/tool_router.py
"""
Central Tool Router and Security Gatekeeper for Red Hat Support AI Agent.

This module acts as the unified execution entry point for all external tool calls.
It enforces a strict whitelist to block unauthorized execution or prompt injection,
routes traffic between direct REST APIs (Jira) and MCP protocols (Salesforce),
normalizes outputs to consistent JSON string formats, and provides defensive error catching.
"""

import json
import sys
from typing import Any, Dict, Union

from tools.jira_adapter import (
    get_comments,
    get_issue,
    search_issues,
)
from tools.mcp_client import call_tool


def execute_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Central security router and dispatcher for external agent tool execution.

    Workflow:
        1. Validates `tool_name` against the allowed tool whitelist.
        2. Routes Jira execution to direct REST endpoints (bypassing MCP).
        3. Routes Salesforce execution through the MCP client layer.
        4. Normalizes all tool outputs into valid JSON strings.
        5. Catches and logs all execution exceptions to protect agent uptime.

    Args:
        tool_name (str): The identifier string of the tool requested for execution.
        args (Dict[str, Any]): Dictionary of arguments passed to the specific tool function.

    Returns:
        str: JSON-formatted string representation of the tool execution result,
             or JSON error message string on failure/unauthorized calls.
    """
    # ---------------------------------------------------
    # AUTHORIZED TOOL WHITELIST
    # ---------------------------------------------------
    # Strictly enforce allowed tools to prevent arbitrary execution or prompt injection attacks
    allowed_tools = [
        # Salesforce Tools (via MCP backend)
        "get_support_case",
        "search_cases",
        "search_historical_cases",
        "list_case_comments",
        # Jira Tools (via direct REST API)
        "jira.get_issue",
        "jira.search",
        "jira.get_comments",
    ]

    # ---------------------------------------------------
    # SECURITY GATEKEEPER CHECK
    # ---------------------------------------------------
    if tool_name not in allowed_tools:
        error_msg = f"Security Violation: Unauthorized tool call attempted: {tool_name}"
        sys.stderr.write(f"[Router] {error_msg}\n")
        return json.dumps({"error": error_msg})

    try:
        sys.stderr.write(f"[Router] Routing tool: {tool_name}\n")

        # ---------------------------------------------------
        # PATH 1: DIRECT JIRA REST ROUTING
        # ---------------------------------------------------
        # Jira bypasses MCP due to OAuth header constraints in serverless/backend contexts
        if tool_name == "jira.get_issue":
            issue_key = args.get("issue_key")
            if not issue_key:
                return json.dumps({"error": "Missing required argument: 'issue_key'"})
            result = get_issue(issue_key)

        elif tool_name == "jira.search":
            jql = args.get("jql")
            if not jql:
                return json.dumps({"error": "Missing required argument: 'jql'"})
            result = search_issues(jql, max_results=args.get("max_results", 5))

        elif tool_name == "jira.get_comments":
            issue_key = args.get("issue_key")
            if not issue_key:
                return json.dumps({"error": "Missing required argument: 'issue_key'"})
            result = get_comments(issue_key)

        # ---------------------------------------------------
        # PATH 2: MCP ROUTING (Salesforce / MCP Tools)
        # ---------------------------------------------------
        else:
            result = call_tool(tool_name, args)

        # ---------------------------------------------------
        # DEFENSIVE RESULT NORMALIZATION
        # ---------------------------------------------------
        # Prevent null or empty string responses from disrupting downstream LLM parser
        if result is None or result == "":
            sys.stderr.write(f"[Router] Warning: {tool_name} returned empty result.\n")
            return "[]"

        # Ensure output return format is always a valid JSON string
        if not isinstance(result, str):
            return json.dumps(result)

        return result

    except Exception as e:
        # ---------------------------------------------------
        # CRITICAL FAIL-SAFE
        # ---------------------------------------------------
        # Log error to stderr and return structured error JSON so agent can adjust instead of retrying
        error_payload = {"error": f"Critical Error executing {tool_name}: {str(e)}"}
        sys.stderr.write(f"[Router] {error_payload['error']}\n")
        return json.dumps(error_payload)
