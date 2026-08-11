# mcp_servers/salesforce_server.py
"""
Salesforce FastMCP Server for Red Hat Support Integration.

This module exposes Red Hat Salesforce Support API operations as MCP tools.
It handles authentication token validation, REST API calls, payload normalization,
chronological case context extraction, and structured stderr logging.
"""

import json
import os
import sys
from typing import Any, Dict, List

import requests
from mcp.server.fastmcp import FastMCP

# -------------------------------------------------------------
# MCP SERVER & ENDPOINT INITIALIZATION
# -------------------------------------------------------------
mcp = FastMCP("redhat-salesforce-server")

SF_BASE_URL = "https://api.access.redhat.com/support/v1/cases"
SF_SEARCH_BASE_URL = "https://api.access.redhat.com/support/search/v2/cases"


# -------------------------------------------------------------
# AUTHENTICATION HELPER
# -------------------------------------------------------------
def get_sf_headers() -> Dict[str, str]:
    """
    Builds the HTTP headers required for Salesforce API requests.

    Retrieves the bearer token from the TOKEN environment variable and
    constructs the authorization and content negotiation headers used by
    all Salesforce REST API calls.

    Returns:
        Dict[str, str]: HTTP headers for authenticated Salesforce API requests.

    Raises:
        ValueError: If the TOKEN environment variable is not configured.
    """
    token = os.getenv("TOKEN")

    if not token:
        raise ValueError("TOKEN environment variable missing")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# -------------------------------------------------------------
# MCP TOOL: CASE CONTEXT REDUCTION UTILITY
# -------------------------------------------------------------
@mcp.tool()
def extract_key_case_context(
    raw_case_data: Dict[str, Any], raw_comments_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Extracts chronological extremes from raw case and comment API payloads.

    Slices multi-page comment histories into:
    1. Initial Problem Statement (First comment / description)
    2. Latest Status (Top 4 most recent comments)
    3. External Jira Trackers (externalTrackers metadata)

    Reduces context window payload size while preserving core troubleshooting signal.
    """
    if not isinstance(raw_comments_data, list):
        raw_comments_data = []

    # 1. Sort comments chronologically by creation date
    sorted_comments = sorted(
        raw_comments_data,
        key=lambda c: c.get("createdDate", "") or c.get("created_date", ""),
    )

    # 2. Extract First Comment / Initial Statement (The "What & Why")
    first_comment = sorted_comments[0] if sorted_comments else None

    # 3. Extract Top 4 Most Recent Comments (The "Where things stand now")
    recent_comments = sorted_comments[-4:] if len(sorted_comments) > 1 else []

    # 4. Extract external Jira trackers metadata (externalTrackers)
    external_trackers = raw_case_data.get("externalTrackers", [])
    jira_keys = []
    if isinstance(external_trackers, list):
        for tracker in external_trackers:
            if isinstance(tracker, dict) and tracker.get("issueKey"):
                jira_keys.append(
                    {
                        "key": tracker.get("issueKey"),
                        "status": tracker.get("status", "Unknown"),
                        "title": tracker.get("title", ""),
                    }
                )

    # 5. Build reduced context payload
    return {
        "case_number": raw_case_data.get("caseNumber") or raw_case_data.get("id"),
        "subject": raw_case_data.get("subject") or raw_case_data.get("summary"),
        "description": raw_case_data.get("description"),
        "initial_comment": (
            {
                "author": first_comment.get("createdByName", "Customer"),
                "date": first_comment.get("createdDate"),
                "body": first_comment.get("body"),
            }
            if first_comment
            else None
        ),
        "latest_updates": [
            {
                "author": c.get("createdByName", "Support Engineer"),
                "date": c.get("createdDate"),
                "body": c.get("body"),
            }
            for c in recent_comments
        ],
        "linked_jira_trackers": jira_keys,
    }


# -------------------------------------------------------------
# MCP TOOL: GET CASE DETAILS
# -------------------------------------------------------------
@mcp.tool()
def get_support_case(case_id: str) -> Dict[str, Any]:
    """
    Retrieves primary details of a specific Red Hat support case.

    Queries the Salesforce Support API for a case number and returns a
    normalized subset of case metadata including summary, status, severity,
    product, description, and linked external trackers.

    Args:
        case_id (str): Red Hat support case number (e.g., 8-digit numeric ID).

    Returns:
        Dict[str, Any]: Normalized case information or an error payload dict on failure.
    """
    url = f"{SF_BASE_URL}/{case_id}"

    try:
        sys.stderr.write(f"[DEBUG] Fetching case: {case_id}\n")

        response = requests.get(url, headers=get_sf_headers(), timeout=15)
        sys.stderr.write(f"[DEBUG] Salesforce STATUS: {response.status_code}\n")

        if response.status_code != 200:
            sys.stderr.write(f"[ERROR] Salesforce Error: {response.text}\n")
            return {
                "error": f"Case {case_id} not found",
                "status": response.status_code,
            }

        data = response.json()

        return {
            "caseNumber": (data.get("caseNumber") or data.get("number") or case_id),
            "summary": (data.get("summary") or data.get("title") or "No Summary"),
            "status": (data.get("status") or "Unknown"),
            "severity": (data.get("severity") or "Normal"),
            "product": (data.get("product") or "N/A"),
            "description": (data.get("description") or "No description provided."),
            "externalTrackers": (data.get("externalTrackers") or []),
        }

    except Exception as e:
        sys.stderr.write(f"[CRITICAL] get_support_case failed: {str(e)}\n")
        return {"error": str(e)}


# -------------------------------------------------------------
# MCP TOOL: LIST CASE COMMENTS
# -------------------------------------------------------------
@mcp.tool()
def list_case_comments(case_number: str) -> List[Any]:
    """
    Retrieves all technical comments associated with a Red Hat support case.

    Args:
        case_number (str): Red Hat support case number.

    Returns:
        List[Any]: List of technical comment dictionary objects, or an empty list if
                   no comments exist or an error occurs.
    """
    url = f"{SF_BASE_URL}/{case_number}/comments"

    try:
        response = requests.get(url, headers=get_sf_headers(), timeout=15)
        sys.stderr.write(f"[DEBUG] Comments STATUS: {response.status_code}\n")

        if response.status_code == 200:
            return response.json()

        sys.stderr.write(f"[ERROR] Comments Error: {response.text}\n")
        return []

    except Exception as e:
        sys.stderr.write(f"[ERROR] list_case_comments failed: {str(e)}\n")
        return []


# -------------------------------------------------------------
# MCP TOOL: GET EXTERNAL TRACKER UPDATES
# -------------------------------------------------------------
@mcp.tool()
def get_external_updates(case_number: str) -> List[Any]:
    """
    Retrieves external tracker updates (Jira/Bugzilla) linked to a support case.

    Args:
        case_number (str): Red Hat support case number.

    Returns:
        List[Any]: List of external tracker updates, or an empty list on failure.
    """
    url = f"{SF_BASE_URL}/{case_number}/externaltrackerupdates"

    try:
        response = requests.get(url, headers=get_sf_headers(), timeout=15)
        sys.stderr.write(f"[DEBUG] External Tracker STATUS: {response.status_code}\n")

        if response.status_code == 200:
            return response.json()

        sys.stderr.write(f"[ERROR] External Tracker Error: {response.text}\n")
        return []

    except Exception as e:
        sys.stderr.write(f"[ERROR] get_external_updates failed: {str(e)}\n")
        return []


# -------------------------------------------------------------
# MCP TOOL: FILTER ACTIVE CASES
# -------------------------------------------------------------
@mcp.tool()
def search_cases(sbrs: List[str] = None, maxResults: int = 20) -> Dict[str, Any]:
    """
    Searches active Red Hat support cases using operational filters.

    Filters cases by predefined operational statuses and SBR identifiers for operational
    case tracking.

    Args:
        sbrs (List[str], optional): List of SBR identifier strings. Defaults to None.
        maxResults (int, optional): Max cases to return. Defaults to 20.

    Returns:
        Dict[str, Any]: Payload containing matching cases array or an error message dict.
    """
    url = f"{SF_BASE_URL}/filter"

    payload = {
        "statuses": [
            "Waiting on Red Hat",
            "Waiting on Engineering",
            "Waiting on Customer",
        ],
        "sbrs": sbrs or [],
        "maxResults": maxResults,
        "sortField": "lastModifiedDate",
        "sortOrder": "desc",
    }

    try:
        response = requests.post(
            url, headers=get_sf_headers(), json=payload, timeout=15
        )
        sys.stderr.write(f"[DEBUG] Search STATUS: {response.status_code}\n")

        response.raise_for_status()
        data = response.json()

        return {"cases": (data if isinstance(data, list) else [data])}

    except Exception as e:
        sys.stderr.write(f"[ERROR] search_cases failed: {str(e)}\n")
        return {"error": f"Search failed: {str(e)}"}


# -------------------------------------------------------------
# MCP TOOL: HISTORICAL SEARCH (SOLR SEARCH v2)
# -------------------------------------------------------------
@mcp.tool()
def search_historical_cases(
    query: str, rows: int = 5, start: int = 0
) -> Dict[str, Any]:
    """
    Executes a full-text search across historical Red Hat support cases.

    Queries the Search v2 API endpoint (`/support/search/v2/cases`) to locate
    historical case documents matching error patterns, symptoms, or keywords for investigation workflows.

    Args:
        query (str): Free-text query terms.
        rows (int, optional): Max documents to retrieve. Defaults to 5.
        start (int, optional): Pagination offset. Defaults to 0.

    Returns:
        Dict[str, Any]: Dictionary containing query metadata, retrieved Solr documents list,
                        and raw results.
    """
    payload = {"q": query, "rows": rows, "start": start}

    try:
        sys.stderr.write(
            f"[DEBUG] Historical Search Query: '{query}' (rows={rows}, start={start})\n"
        )

        headers = get_sf_headers()
        response = requests.post(
            SF_SEARCH_BASE_URL, headers=headers, json=payload, timeout=30
        )

        sys.stderr.write(f"[DEBUG] Historical Search STATUS: {response.status_code}\n")

        if response.status_code != 200:
            sys.stderr.write(f"[ERROR] Historical Search Error: {response.text}\n")
            return {
                "error": f"Historical search failed ({response.status_code})",
                "status": response.status_code,
                "details": response.text,
                "cases": [],
            }

        data = response.json()

        # Extract Solr documents array from .response.docs
        docs = []
        if isinstance(data, dict):
            docs = data.get("response", {}).get("docs", [])

        return {
            "query": query,
            "start": start,
            "rows": rows,
            "cases": docs,
            "results": data,
        }

    except Exception as e:
        sys.stderr.write(f"[ERROR] search_historical_cases failed: {str(e)}\n")
        return {"error": str(e), "cases": []}


# -------------------------------------------------------------
# SERVER EXECUTION ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
