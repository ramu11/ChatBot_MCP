import base64
import json
import os
import sys
from typing import Any, Dict, List, Optional
import requests
from mcp.server.fastmcp import FastMCP

# ------------------------------------------------
# MCP SERVER
# ------------------------------------------------
mcp = FastMCP("atlassian-jira-server")

# ------------------------------------------------
# ATLASSIAN REMOTE MCP ENDPOINT & SESSION
# ------------------------------------------------
ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp"
session = requests.Session()


# ------------------------------------------------
# AUTH HEADERS
# ------------------------------------------------
def get_mcp_headers() -> Dict[str, str]:
    email = os.getenv("ATLASSIAN_EMAIL")
    token = os.getenv("ATLASSIAN_TOKEN")

    if not email or not token:
        raise ValueError(
            "Missing environment variables: ATLASSIAN_EMAIL and ATLASSIAN_TOKEN must be set."
        )

    auth_string = f"{email}:{token}"
    encoded = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ------------------------------------------------
# GENERIC MCP CALLER
# ------------------------------------------------
def call_remote_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": f"{tool_name}-request",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    sys.stderr.write(f"\n[DEBUG] MCP TOOL: {tool_name}\n")
    sys.stderr.write(f"[DEBUG] MCP PAYLOAD: {json.dumps(payload)}\n")

    try:
        response = session.post(
            ATLASSIAN_MCP_URL, headers=get_mcp_headers(), json=payload, timeout=60
        )

        sys.stderr.write(f"[DEBUG] MCP STATUS: {response.status_code}\n")
        sys.stderr.write(f"[DEBUG] MCP RESPONSE: {response.text[:2000]}\n")

        if response.status_code == 404:
            issue_key = arguments.get("issueKey", "requested issue")
            return {"error": f"Jira issue {issue_key} not found or access restricted"}

        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        sys.stderr.write(f"[ERROR] Remote MCP HTTP Error: {str(http_err)}\n")
        issue_key = arguments.get("issueKey", "requested issue")
        return {
            "error": f"HTTP error while accessing Jira issue {issue_key}: {str(http_err)}"
        }
    except Exception as err:
        sys.stderr.write(f"[ERROR] Remote MCP Request Error: {str(err)}\n")
        return {"error": f"Remote MCP call failed: {str(err)}"}


# ------------------------------------------------
# HELPERS
# ------------------------------------------------
def flatten_adf(node: Any) -> str:
    """Recursively parses and flattens Atlassian Document Format (ADF) into text."""
    if isinstance(node, list):
        return "".join(flatten_adf(item) for item in node)

    if isinstance(node, dict):
        node_type = node.get("type")

        if node_type == "text":
            return node.get("text", "")
        if node_type == "hardBreak":
            return "\n"
        if node_type == "paragraph":
            return flatten_adf(node.get("content", [])) + "\n"
        if node_type in ("bulletList", "orderedList"):
            return "\n" + flatten_adf(node.get("content", []))
        if node_type == "listItem":
            return " • " + flatten_adf(node.get("content", []))

        return flatten_adf(node.get("content", []))

    return ""


def extract_issue_from_mcp_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    result = response_data.get("result", {})

    if isinstance(result, dict):
        if result.get("key"):
            return result

        if isinstance(result.get("issue"), dict):
            return result["issue"]

        content = result.get("content", [])
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                text = first.get("text")
                if text and isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            if parsed.get("key"):
                                return parsed
                            if parsed.get("issue"):
                                return parsed["issue"]
                    except (json.JSONDecodeError, TypeError):
                        pass

    return {}


def extract_comments_list(
    issue_obj: Dict[str, Any], fields_obj: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Safely finds comments list across different Atlassian API structures."""
    # 1. Standard Jira REST API v3: issue.fields.comment.comments
    comment_field = fields_obj.get("comment")
    if isinstance(comment_field, dict) and isinstance(
        comment_field.get("comments"), list
    ):
        return comment_field["comments"]

    # 2. Alternative array location: issue.fields.comment as a list
    if isinstance(comment_field, list):
        return comment_field

    # 3. Direct comments array on issue object
    if isinstance(issue_obj.get("comments"), list):
        return issue_obj["comments"]

    return []


# ------------------------------------------------
# GET JIRA DETAILS TOOL
# ------------------------------------------------
@mcp.tool()
def get_jira_details(jira_id: str) -> Dict[str, Any]:
    try:
        sys.stderr.write(f"\n[DEBUG] FETCHING JIRA: {jira_id}\n")

        candidate_tools = [
            "getJiraIssue",
            "jira.getIssue",
            "get_issue",
            "jira_get_issue",
        ]

        last_error: Optional[str] = None
        issue: Dict[str, Any] = {}

        for tool_name in candidate_tools:
            try:
                # Requesting comments explicitly via expand parameter
                response_data = call_remote_mcp_tool(
                    tool_name,
                    {"issueKey": jira_id, "expand": "renderedFields,comments"},
                )

                # Check if the response itself is an error dictionary from call_remote_mcp_tool
                if isinstance(response_data, dict) and "error" in response_data:
                    last_error = response_data["error"]
                    continue

                issue = extract_issue_from_mcp_response(response_data)

                if issue:
                    sys.stderr.write(f"[DEBUG] SUCCESS TOOL: {tool_name}\n")
                    break
            except Exception as tool_error:
                last_error = str(tool_error)
                sys.stderr.write(f"[DEBUG] TOOL FAILED: {tool_name} -> {last_error}\n")

        if not issue:
            return {
                "error": f"Jira issue {jira_id} not found or access restricted. Details: {last_error}"
            }

        fields = issue.get("fields", {})

        # Extract Comments safely
        raw_comments = extract_comments_list(issue, fields)
        recent_comments: List[Dict[str, str]] = []

        for c in raw_comments[-5:]:  # Retrieve last 5 comments
            if not isinstance(c, dict):
                continue

            body = c.get("body")
            plain_text = (
                flatten_adf(body) if isinstance(body, (dict, list)) else str(body or "")
            )

            author_info = c.get("author", {})
            author_name = (
                author_info.get("displayName") or author_info.get("name") or "Engineer"
            )

            if plain_text.strip():
                recent_comments.append(
                    {
                        "author": author_name,
                        "body": plain_text.strip(),
                        "created": c.get("created", ""),
                    }
                )

        return {
            "key": issue.get("key", jira_id),
            "href": f"https://redhat.atlassian.net/browse/{jira_id}",
            "status": fields.get("status", {}).get("name", "Unknown"),
            "summary": fields.get("summary") or "No Summary",
            "priority": fields.get("priority", {}).get("name", "None"),
            "issue_type": fields.get("issuetype", {}).get("name", "Unknown"),
            "components": [
                c.get("name")
                for c in fields.get("components", [])
                if isinstance(c, dict)
            ],
            "versions": [
                v.get("name")
                for v in fields.get("fixVersions", [])
                if isinstance(v, dict)
            ],
            "description": flatten_adf(fields.get("description", {})).strip()[:2000],
            "recent_comments": recent_comments,
            "created": fields.get("created"),
            "updated": fields.get("updated"),
        }

    except Exception as e:
        sys.stderr.write(f"[CRITICAL] Jira MCP failed: {str(e)}\n")
        return {
            "error": f"Jira issue {jira_id} not found or access restricted: {str(e)}"
        }


# ------------------------------------------------
# ADD JIRA COMMENT TOOL
# ------------------------------------------------
@mcp.tool()
def add_jira_comment(jira_id: str, comment_text: str) -> Dict[str, Any]:
    """Adds a new comment to a specified Jira issue."""
    try:
        candidate_tools = ["addCommentToJiraIssue", "jira.addComment", "add_comment"]

        last_error: Optional[str] = None

        for tool_name in candidate_tools:
            try:
                res = call_remote_mcp_tool(
                    tool_name, {"issueKey": jira_id, "comment": comment_text}
                )
                if isinstance(res, dict) and "error" in res:
                    last_error = res["error"]
                    continue
                return res
            except Exception as tool_error:
                last_error = str(tool_error)
                sys.stderr.write(
                    f"[DEBUG] COMMENT TOOL FAILED: {tool_name} -> {last_error}\n"
                )

        return {"error": f"Failed to add comment. Last error: {last_error}"}

    except Exception as e:
        sys.stderr.write(f"[CRITICAL] Add Jira Comment failed: {str(e)}\n")
        return {"error": str(e)}


# ------------------------------------------------
# SEARCH JIRA TOOL
# ------------------------------------------------
@mcp.tool()
def search_jira(jql: str, limit: int = 10) -> Dict[str, Any]:
    try:
        candidate_tools = [
            "searchJiraIssuesUsingJql",
            "searchJiraIssues",
            "jira.search",
            "search_issues",
        ]

        last_error: Optional[str] = None

        for tool_name in candidate_tools:
            try:
                res = call_remote_mcp_tool(tool_name, {"jql": jql, "limit": limit})
                if isinstance(res, dict) and "error" in res:
                    last_error = res["error"]
                    continue
                return res
            except Exception as tool_error:
                last_error = str(tool_error)
                sys.stderr.write(
                    f"[DEBUG] SEARCH TOOL FAILED: {tool_name} -> {last_error}\n"
                )

        return {"error": f"All Jira search tools failed. Last error: {last_error}"}

    except Exception as e:
        sys.stderr.write(f"[CRITICAL] Jira Search failed: {str(e)}\n")
        return {"error": str(e)}


# ------------------------------------------------
# MAIN
# ------------------------------------------------
if __name__ == "__main__":
    sys.stderr.write("\n[INFO] Starting Atlassian Jira MCP Server\n")
    mcp.run(transport="stdio")
