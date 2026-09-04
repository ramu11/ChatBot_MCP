# tools/tool_router.py
"""
Central Dispatch Router for Support Agent Tool Execution.

This module routes tool invocation requests from the orchestrator or agent logic to
either local MCP stdio servers (Salesforce) or direct REST endpoints (Jira).
"""

import json
import os
import sys
from typing import Any, Dict

import requests
import urllib3
from tools.mcp_client import call_tool as call_mcp_tool

# Suppress unverified HTTPS warnings for corporate gateway compatibility
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Target environment parameters for direct REST integrations
JIRA_URL = os.getenv("JIRA_BASE_URL")
JIRA_BEARER_TOKEN = os.getenv("JIRA_BEARER_TOKEN")


# -------------------------------------------------------------
# SAFE JSON PARSER HELPER
# -------------------------------------------------------------
def _safe_json_loads(data: str) -> Any:
    """
    Safely attempts to parse JSON text without raising exceptions.
    """
    try:
        if isinstance(data, str) and data.strip():
            return json.loads(data)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# -------------------------------------------------------------
# DIRECT REST JIRA EXECUTOR
# -------------------------------------------------------------
def execute_jira_rest(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Executes Jira API operations directly over HTTP REST calls.

    Args:
        tool_name (str): Identifier for Jira tool (e.g. "jira.get_issue", "jira.get_comments").
        args (Dict[str, Any]): Parameters containing "issue_key".

    Returns:
        str: JSON string of HTTP response or error payload.
    """
    if not isinstance(args, dict):
        args = {}

    issue_key = args.get("issue_key")
    if not issue_key:
        return json.dumps({"error": "Missing required 'issue_key' parameter."})

    jira_base_url = (JIRA_URL).rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if JIRA_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {JIRA_BEARER_TOKEN}"

    try:
        if tool_name == "jira.get_issue":
            url = f"{jira_base_url}/rest/api/2/issue/{issue_key}"
        elif tool_name == "jira.get_comments":
            url = f"{jira_base_url}/rest/api/2/issue/{issue_key}/comment"
        else:
            return json.dumps({"error": f"Unknown Jira REST tool: {tool_name}"})

        sys.stderr.write(f"[JIRA REST] Invoking GET {url}\n")
        response = requests.get(url, headers=headers, verify=False, timeout=15)

        if not response.ok:
            sys.stderr.write(
                f"[JIRA REST ERROR] Status {response.status_code}: {response.text}\n"
            )
            return json.dumps(
                {
                    "error": f"Jira REST request failed with status {response.status_code}",
                    "status_code": response.status_code,
                    "details": response.text[:200],
                }
            )

        parsed_json = _safe_json_loads(response.text)
        return (
            json.dumps(parsed_json) if isinstance(parsed_json, dict) else response.text
        )

    except requests.exceptions.RequestException as e:
        sys.stderr.write(f"[JIRA REST Connection Exception]: {str(e)}\n")
        return json.dumps({"error": f"Jira REST connection failed: {str(e)}"})


# -------------------------------------------------------------
# MAIN TOOL ROUTER ENTRY POINT
# -------------------------------------------------------------
def execute_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Dispatches tool execution calls based on prefix identifier.

    Args:
        tool_name (str): Fully qualified tool name (e.g. "get_support_case", "jira.get_issue").
        args (Dict[str, Any]): Dictionary of arguments.

    Returns:
        str: JSON string output from tool execution.
    """
    if not isinstance(args, dict):
        args = {}

    sys.stderr.write(
        f"[TOOL ROUTER] Routing '{tool_name}' with args: {json.dumps(args)}\n"
    )

    try:
        # Route 1: Jira Direct REST API tools
        if tool_name.startswith("jira."):
            return execute_jira_rest(tool_name, args)

        # Route 2: MCP Salesforce tools (strip prefix if present)
        mcp_tool_name = tool_name
        if tool_name.startswith("salesforce."):
            mcp_tool_name = tool_name.replace("salesforce.", "")

        return call_mcp_tool(mcp_tool_name, args)

    except Exception as e:
        sys.stderr.write(f"[TOOL ROUTER CRITICAL ERROR] Execution failed: {str(e)}\n")
        return json.dumps({"error": f"Tool Router Error: {str(e)}"})
