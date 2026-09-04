"""
Jira Adapter Module (located in tools/jira_adapter.py)

Handles direct interaction with Jira REST API v3 as well as
parsing, extraction, parallel enrichment, and Markdown formatting of Jira tickets.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from typing import Any, Dict, List
import requests

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")

EMAIL = os.getenv("EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")


def _auth():
    return (EMAIL, JIRA_TOKEN)


# -------------------------------------------------------------
# DIRECT JIRA REST API CALLS
# -------------------------------------------------------------
def get_issue(issue_key: str) -> Dict[str, Any]:
    """Fetches full Jira issue payload from REST API v3."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    try:
        res = requests.get(url, auth=_auth(), timeout=15)
        if res.status_code == 404:
            return {"error": f"Jira issue {issue_key} not found or access restricted"}
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as e:
        return {
            "error": f"HTTP error occurred while fetching issue {issue_key}: {str(e)}"
        }
    except Exception as e:
        return {"error": f"Failed to fetch Jira issue {issue_key}: {str(e)}"}


def search_issues(jql: str, max_results: int = 5) -> Dict[str, Any]:
    """Executes a JQL query search against Jira REST API v3."""
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    payload = {"jql": jql, "maxResults": max_results}
    try:
        res = requests.post(url, json=payload, auth=_auth(), timeout=15)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP error during JQL search: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to perform JQL search: {str(e)}"}


def get_comments(issue_key: str) -> Dict[str, Any]:
    """Fetches comments for a specific Jira issue from REST API v3."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    try:
        res = requests.get(url, auth=_auth(), timeout=15)
        if res.status_code == 404:
            return {
                "error": f"Comments for Jira issue {issue_key} not found or access restricted"
            }
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as e:
        return {
            "error": f"HTTP error occurred while fetching comments for {issue_key}: {str(e)}"
        }
    except Exception as e:
        return {
            "error": f"Failed to fetch comments for Jira issue {issue_key}: {str(e)}"
        }


# -------------------------------------------------------------
# EXTRACTION & HELPER UTILITIES
# -------------------------------------------------------------
def safe_json_loads(data: Any) -> Dict[str, Any]:
    """Safely parses JSON input payloads without raising uncaught exceptions."""
    try:
        if isinstance(data, str) and data.strip():
            return json.loads(data)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def extract_jira_details(data_obj: Any) -> List[Dict[str, str]]:
    """Scans arbitrary data objects or text payloads to identify standard Jira ticket keys."""
    if not data_obj:
        return []

    jira_pattern = r"\b([A-Z]{2,10}-[0-9]+)\b"
    raw_text = json.dumps(data_obj) if not isinstance(data_obj, str) else data_obj
    found_ids = set(re.findall(jira_pattern, raw_text))

    return [{"id": jid} for jid in found_ids]


# -------------------------------------------------------------
# JIRA ENRICHMENT & TABLE UTILITIES
# -------------------------------------------------------------
def fetch_single_jira_summary(jid: str, execute_tool_fn) -> Dict[str, Any]:
    """Fetches details and top comments for a single Jira ticket."""
    try:
        jira_raw = execute_tool_fn("jira.get_issue", {"issue_key": jid})
        issue = safe_json_loads(jira_raw)

        if not isinstance(issue, dict) or not issue or "error" in issue:
            return {
                "key": jid,
                "error": (
                    issue.get("error", "Failed to retrieve Jira ticket")
                    if isinstance(issue, dict)
                    else "Invalid payload"
                ),
            }

        fields = issue.get("fields", {})

        comments_raw = execute_tool_fn("jira.get_comments", {"issue_key": jid})
        comments_data = safe_json_loads(comments_raw)
        comments = (
            comments_data.get("comments") if isinstance(comments_data, dict) else []
        )

        recent_comments = []
        if isinstance(comments, list):
            for c in comments[-5:]:
                if isinstance(c, dict):
                    body = str(c.get("body", "")).strip()
                    if body and len(body) > 20:
                        recent_comments.append(
                            {
                                "author": (
                                    c.get("author", {}).get("displayName", "Engineer")
                                    if isinstance(c.get("author"), dict)
                                    else "Engineer"
                                ),
                                "body": body[:400],
                            }
                        )

        return {
            "key": issue.get("key", jid),
            "href": f"https://redhat.atlassian.net/browse/{issue.get('key', jid)}",
            "status": (
                fields.get("status", {}).get("name", "Unknown")
                if isinstance(fields.get("status"), dict)
                else "Unknown"
            ),
            "summary": fields.get("summary") or "No Summary",
            "priority": (
                fields.get("priority", {}).get("name", "None")
                if isinstance(fields.get("priority"), dict)
                else "None"
            ),
            "components": [
                c.get("name")
                for c in fields.get("components", [])
                if isinstance(c, dict) and c.get("name")
            ],
            "versions": [
                v.get("name")
                for v in fields.get("fixVersions", [])
                if isinstance(v, dict) and v.get("name")
            ],
            "description": str(fields.get("description") or "")[:500],
            "recent_comments": recent_comments,
        }
    except Exception as e:
        return {"key": jid, "error": str(e)}


def batch_fetch_jiras(jira_ids: List[str], execute_tool_fn) -> List[Dict[str, Any]]:
    """Fetches up to 5 Jira tickets concurrently using ThreadPoolExecutor."""
    results = []
    unique_jids = list(dict.fromkeys(jira_ids))[:5]

    with ThreadPoolExecutor(max_workers=min(len(unique_jids), 5)) as executor:
        future_to_jid = {
            executor.submit(fetch_single_jira_summary, jid, execute_tool_fn): jid
            for jid in unique_jids
        }
        for future in as_completed(future_to_jid):
            results.append(future.result())

    return results


def fetch_jira_api_data(jira_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Sequential fallback utility to fetch Jira API data."""
    from .tool_router import execute_tool

    jids = [j.get("id") for j in jira_list if j.get("id")]
    return batch_fetch_jiras(jids, execute_tool)


def build_jira_table(jiras: List[Dict[str, Any]]) -> str:
    """Formats enriched Jira metadata lists into clean Markdown tables for UI display."""
    if not jiras:
        return "No Jira data available."

    header = (
        "| Jira | Status | Summary | Priority | Components | Versions |\n"
        "|------|--------|---------|----------|------------|----------|\n"
    )

    rows = ""
    for j in jiras:
        key = j.get("key", j.get("id", "N/A"))
        href = j.get("href") or ""
        jira_link = f"[{key}]({href})" if href else key

        components = ", ".join(j.get("components") or []) or "None"
        versions = ", ".join(j.get("versions") or []) or "None"

        rows += (
            f"| {jira_link} "
            f"| {j.get('status') or 'Unknown'} "
            f"| {j.get('summary') or 'No Summary'} "
            f"| {j.get('priority') or 'None'} "
            f"| {components} "
            f"| {versions} |\n"
        )

    return header + rows
