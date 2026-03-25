import requests
import os
import sys
import json
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("redhat-support-server")

# Endpoints
SF_BASE_URL = "https://api.access.redhat.com/support/v1/cases"
JIRA_API_URL = "https://redhat.atlassian.net/rest/api/3/issue"


def get_sf_headers():
    """Helper to pull the Red Hat Salesforce API Token."""
    token = os.getenv("TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


def get_jira_auth():
    """Helper for Jira Basic Auth credentials mirroring curl -u."""
    email = os.getenv("EMAIL")
    jira_token = os.getenv("JIRA_TOKEN")

    # 🔍 Debug logs (safe)
    sys.stderr.write(f"[DEBUG] EMAIL: {email}\n")
    sys.stderr.write(f"[DEBUG] TOKEN LENGTH: {len(jira_token) if jira_token else 0}\n")

    return (email, jira_token)


def flatten_adf(node):
    """Recursively converts Jira ADF JSON to plain text."""
    if isinstance(node, list):
        return "".join(flatten_adf(item) for item in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        return flatten_adf(node.get("content", []))
    return ""


@mcp.tool()
def get_support_case(case_id: str) -> Dict[str, Any]:
    """
    Fetch primary details for a specific 8-digit Red Hat support case.
    """
    url = f"{SF_BASE_URL}/{case_id}"
    try:
        sys.stderr.write(f"[DEBUG] Fetching case: {case_id}\n")

        response = requests.get(url, headers=get_sf_headers(), timeout=15)

        if response.status_code != 200:
            sys.stderr.write(f"[ERROR] Salesforce returned {response.status_code}\n")
            return {"error": f"Case {case_id} not found", "status": response.status_code}

        data = response.json()

        return {
            "caseNumber": data.get("caseNumber") or data.get("number") or case_id,
            "summary": data.get("summary") or data.get("title") or "No Summary",
            "status": data.get("status") or "Unknown",
            "severity": data.get("severity") or "Normal",
            "product": data.get("product") or "N/A",
            "description": data.get("description") or "No description provided.",
            "externalTrackers": data.get("externalTrackers") or []
        }

    except Exception as e:
        sys.stderr.write(f"[CRITICAL] get_support_case failed: {str(e)}\n")
        return {"error": str(e)}


@mcp.tool()
def get_jira_details(jira_id: str) -> Dict[str, Any]:
    url = f"{JIRA_API_URL}/{jira_id}"
    headers = {"Accept": "application/json"}

    try:
        sys.stderr.write(f"[DEBUG] Jira ID: {jira_id}\n")

        auth = get_jira_auth()

        res = requests.get(url, auth=auth, headers=headers, timeout=15)

        sys.stderr.write(f"[DEBUG] Jira API STATUS: {res.status_code}\n")

        if res.status_code != 200:
            sys.stderr.write(f"[ERROR] Jira API failed: {res.text}\n")
            return {"error": f"Jira {jira_id} not accessible"}

        data = res.json()
        fields = data.get("fields", {})

        # =========================
        # COMMENTS FIX (PRIMARY SOURCE)
        # =========================
        recent_comments = []

        embedded_comments = fields.get("comment", {}).get("comments", [])

        if embedded_comments:
            for c in embedded_comments[-3:]:
                body = c.get("body")
                plain_text = flatten_adf(body) if isinstance(body, dict) else str(body)

                if plain_text.strip():
                    recent_comments.append({
                        "author": c.get("author", {}).get("displayName", "Engineer"),
                        "body": plain_text.strip()
                    })

        # =========================
        # FALLBACK (API)
        # =========================
        if not recent_comments:
            try:
                c_res = requests.get(
                    f"{url}/comment?maxResults=3&orderBy=-created",
                    auth=auth,
                    headers=headers,
                    timeout=10
                )

                sys.stderr.write(f"[DEBUG] Comments API STATUS: {c_res.status_code}\n")

                if c_res.status_code == 200:
                    comments_data = c_res.json().get("comments", [])

                    for c in comments_data:
                        body = c.get("body")
                        plain_text = flatten_adf(body) if isinstance(body, dict) else str(body)

                        if plain_text.strip():
                            recent_comments.append({
                                "author": c.get("author", {}).get("displayName", "Engineer"),
                                "body": plain_text.strip()
                            })

            except Exception as e:
                sys.stderr.write(f"[ERROR] Comment fallback failed: {str(e)}\n")

        # =========================
        # SAFE FIELD EXTRACTION
        # =========================

        components = [c.get("name") for c in fields.get("components", [])]
        versions = [v.get("name") for v in fields.get("versions", [])]

        description_text = flatten_adf(fields.get("description", {}))

        # Extract errors
        import re
        error_patterns = [
            r"Exception.*",
            r"Error.*",
            r"HTTP\s\d{3}",
            r"status\s<\d+>"
        ]

        errors_found = []
        for pattern in error_patterns:
            errors_found.extend(re.findall(pattern, description_text))

        # Jira HREF (IMPORTANT FIX)
        jira_link = f"https://redhat.atlassian.net/browse/{jira_id}"

        return {
            "key": jira_id,
            "href": jira_link,
            "status": fields.get("status", {}).get("name"),
            "summary": fields.get("summary"),
            "priority": fields.get("priority", {}).get("name"),
            "issue_type": fields.get("issuetype", {}).get("name"),
            "components": components,
            "versions": versions,
            "environment": flatten_adf(fields.get("environment", {})),
            "description": description_text[:1000],
            "errors": list(set(errors_found)),
            "recent_comments": recent_comments,
            "created": fields.get("created"),
            "updated": fields.get("updated")
        }

    except Exception as e:
        sys.stderr.write(f"[CRITICAL] Jira processing failed: {str(e)}\n")
        return {"error": str(e)}


@mcp.tool()
def list_case_comments(case_number: str) -> List[Any]:
    """Retrieve history of technical Salesforce comments."""
    url = f"{SF_BASE_URL}/{case_number}/comments"
    try:
        res = requests.get(url, headers=get_sf_headers(), timeout=15)
        if res.status_code == 200:
            return res.json()
        return []
    except Exception as e:
        sys.stderr.write(f"[ERROR] list_case_comments: {str(e)}\n")
        return []


@mcp.tool()
def get_external_updates(case_number: str) -> List[Any]:
    """Retrieve official Jira/Bugzilla sync data from Salesforce."""
    url = f"{SF_BASE_URL}/{case_number}/externaltrackerupdates"
    try:
        res = requests.get(url, headers=get_sf_headers(), timeout=15)
        if res.status_code == 200:
            return res.json()
        return []
    except Exception as e:
        sys.stderr.write(f"[ERROR] get_external_updates: {str(e)}\n")
        return []


@mcp.tool()
def search_cases(sbrs: List[str] = None, maxResults: int = 20) -> Dict[str, Any]:
    """Search active Red Hat cases."""
    url = f"{SF_BASE_URL}/filter"

    payload = {
        "statuses": ["Waiting on Red Hat", "Waiting on Engineering", "Waiting on Customer"],
        "sbrs": sbrs or [],
        "maxResults": maxResults,
        "sortField": "lastModifiedDate",
        "sortOrder": "desc"
    }

    try:
        res = requests.post(url, headers=get_sf_headers(), json=payload, timeout=15)
        res.raise_for_status()

        data = res.json()

        return {
            "cases": data if isinstance(data, list) else [data]
        }

    except Exception as e:
        sys.stderr.write(f"[ERROR] search_cases failed: {str(e)}\n")
        return {"error": f"Search failed: {str(e)}"}


if __name__ == "__main__":
    mcp.run()
