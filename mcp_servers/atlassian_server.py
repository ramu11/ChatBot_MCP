import requests
import os
import sys
import json
import base64
from typing import Dict, Any, List
from mcp.server.fastmcp import FastMCP

# ------------------------------------------------
# MCP SERVER
# ------------------------------------------------
mcp = FastMCP("atlassian-jira-server")

# ------------------------------------------------
# ATLASSIAN REMOTE MCP ENDPOINT
# ------------------------------------------------
ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp"

# ------------------------------------------------
# AUTH HEADERS
# ------------------------------------------------
def get_mcp_headers():

    email = os.getenv("ATLASSIAN_EMAIL")
    token = os.getenv("ATLASSIAN_TOKEN")

    if not email or not token:
        raise ValueError(
            "ATLASSIAN_EMAIL or ATLASSIAN_TOKEN missing"
        )

    # email:token
    auth_string = f"{email}:{token}"

    # base64(email:token)
    encoded = base64.b64encode(
        auth_string.encode("utf-8")
    ).decode("utf-8")

    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


# ------------------------------------------------
# GENERIC MCP CALLER
# ------------------------------------------------
def call_remote_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any]
) -> Dict[str, Any]:

    payload = {
        "jsonrpc": "2.0",
        "id": f"{tool_name}-request",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    sys.stderr.write(
        f"\n[DEBUG] MCP TOOL: {tool_name}\n"
    )

    sys.stderr.write(
        f"[DEBUG] MCP PAYLOAD: "
        f"{json.dumps(payload)}\n"
    )

    response = requests.post(
        ATLASSIAN_MCP_URL,
        headers=get_mcp_headers(),
        json=payload,
        timeout=60
    )

    sys.stderr.write(
        f"[DEBUG] MCP STATUS: "
        f"{response.status_code}\n"
    )

    sys.stderr.write(
        f"[DEBUG] MCP RESPONSE: "
        f"{response.text[:2000]}\n"
    )

    response.raise_for_status()

    return response.json()


# ------------------------------------------------
# HELPERS
# ------------------------------------------------
def flatten_adf(node):

    if isinstance(node, list):

        return "".join(
            flatten_adf(item)
            for item in node
        )

    if isinstance(node, dict):

        node_type = node.get("type")

        if node_type == "text":
            return node.get("text", "")

        if node_type == "hardBreak":
            return "\n"

        return flatten_adf(
            node.get("content", [])
        )

    return ""


def extract_issue_from_mcp_response(
    response_data: Dict[str, Any]
) -> Dict[str, Any]:

    # MCP response structure varies
    result = response_data.get("result", {})

    if isinstance(result, dict):

        # direct issue
        if result.get("key"):
            return result

        # nested issue
        if isinstance(result.get("issue"), dict):
            return result["issue"]

        # content array
        content = result.get("content", [])

        if content and isinstance(content, list):

            first = content[0]

            if isinstance(first, dict):

                # text field containing JSON
                text = first.get("text")

                if text:
                    try:
                        parsed = json.loads(text)

                        if isinstance(parsed, dict):

                            if parsed.get("key"):
                                return parsed

                            if parsed.get("issue"):
                                return parsed["issue"]

                    except Exception:
                        pass

    return {}


# ------------------------------------------------
# GET JIRA DETAILS
# ------------------------------------------------
@mcp.tool()
def get_jira_details(
    jira_id: str
) -> Dict[str, Any]:

    try:

        sys.stderr.write(
            f"\n[DEBUG] FETCHING JIRA: "
            f"{jira_id}\n"
        )

        # ------------------------------------------------
        # TRY MULTIPLE TOOL NAMES
        # Atlassian MCP naming differs by rollout
        # ------------------------------------------------
        candidate_tools = [
            "getJiraIssue",
            "jira.getIssue",
            "get_issue",
            "jira_get_issue"
        ]

        last_error = None
        issue = {}

        for tool_name in candidate_tools:

            try:

                response_data = call_remote_mcp_tool(
                    tool_name,
                    {
                        "issueKey": jira_id
                    }
                )

                issue = extract_issue_from_mcp_response(
                    response_data
                )

                if issue:
                    sys.stderr.write(
                        f"[DEBUG] SUCCESS TOOL: "
                        f"{tool_name}\n"
                    )
                    break

            except Exception as tool_error:

                last_error = str(tool_error)

                sys.stderr.write(
                    f"[DEBUG] TOOL FAILED: "
                    f"{tool_name} -> "
                    f"{str(tool_error)}\n"
                )

        if not issue:

            return {
                "error": (
                    f"Unable to fetch Jira "
                    f"{jira_id}. "
                    f"Last error: {last_error}"
                )
            }

        fields = issue.get("fields", {})

        # ------------------------------------------------
        # COMMENTS
        # ------------------------------------------------
        comments_obj = (
            fields.get("comment", {})
        )

        comments = comments_obj.get(
            "comments",
            []
        )

        recent_comments: List[Dict[str, str]] = []

        for c in comments[-3:]:

            body = c.get("body")

            plain_text = (
                flatten_adf(body)
                if isinstance(body, dict)
                else str(body)
            )

            if plain_text.strip():

                recent_comments.append({
                    "author": (
                        c.get("author", {})
                        .get(
                            "displayName",
                            "Engineer"
                        )
                    ),
                    "body": plain_text.strip()
                })

        # ------------------------------------------------
        # RETURN NORMALIZED OBJECT
        # ------------------------------------------------
        return {

            "key": issue.get(
                "key",
                jira_id
            ),

            "href": (
                "https://redhat.atlassian.net/browse/"
                f"{jira_id}"
            ),

            "status": (
                fields.get("status", {})
                .get("name", "Unknown")
            ),

            "summary": (
                fields.get("summary")
                or "No Summary"
            ),

            "priority": (
                fields.get("priority", {})
                .get("name", "None")
            ),

            "issue_type": (
                fields.get("issuetype", {})
                .get("name", "Unknown")
            ),

            "components": [
                c.get("name")
                for c in fields.get(
                    "components",
                    []
                )
            ],

            "versions": [
                v.get("name")
                for v in fields.get(
                    "fixVersions",
                    []
                )
            ],

            "description": flatten_adf(
                fields.get(
                    "description",
                    {}
                )
            )[:2000],

            "recent_comments": recent_comments,

            "created": fields.get(
                "created"
            ),

            "updated": fields.get(
                "updated"
            )
        }

    except Exception as e:

        sys.stderr.write(
            f"[CRITICAL] Jira MCP failed: "
            f"{str(e)}\n"
        )

        return {
            "error": str(e)
        }


# ------------------------------------------------
# SEARCH JIRA
# ------------------------------------------------
@mcp.tool()
def search_jira(
    jql: str,
    limit: int = 10
) -> Dict[str, Any]:

    try:

        candidate_tools = [
            "searchJiraIssues",
            "jira.search",
            "search_issues"
        ]

        last_error = None

        for tool_name in candidate_tools:

            try:

                response_data = call_remote_mcp_tool(
                    tool_name,
                    {
                        "jql": jql,
                        "limit": limit
                    }
                )

                return response_data

            except Exception as tool_error:

                last_error = str(tool_error)

                sys.stderr.write(
                    f"[DEBUG] SEARCH TOOL FAILED: "
                    f"{tool_name} -> "
                    f"{str(tool_error)}\n"
                )

        return {
            "error": (
                "All Jira search tools failed. "
                f"Last error: {last_error}"
            )
        }

    except Exception as e:

        sys.stderr.write(
            f"[CRITICAL] Jira Search failed: "
            f"{str(e)}\n"
        )

        return {
            "error": str(e)
        }


# ------------------------------------------------
# MAIN
# ------------------------------------------------
if __name__ == "__main__":

    sys.stderr.write(
        "\n[INFO] Starting Atlassian Jira MCP Server\n"
    )

    mcp.run()


