"""
salesforce_server.py

MCP server providing access to Red Hat Salesforce Support APIs.

Responsibilities:
- Exposes Salesforce support operations as MCP tools.
- Authenticates requests using a Red Hat bearer token.
- Retrieves support case details, comments, external tracker updates,
  and historical case search results.
- Translates MCP tool invocations into Salesforce REST API requests.
- Returns normalized JSON responses for consumption by the AI agent.

Exposed MCP Tools:
- get_support_case()
- list_case_comments()
- get_external_updates()
- search_cases()
- search_historical_cases()

This server acts as the Salesforce integration layer for the AI Support
Copilot and encapsulates all Salesforce API communication behind MCP.
The agent interacts only with MCP tools and remains independent of the
underlying Salesforce REST endpoints.
"""

import requests
import os
import sys
import json
from typing import List, Dict, Any

from mcp.server.fastmcp import FastMCP

# ------------------------------------------------
# MCP SERVER
# ------------------------------------------------
mcp = FastMCP("redhat-salesforce-server")


# ------------------------------------------------
# SALESFORCE ENDPOINT
# ------------------------------------------------
SF_BASE_URL = "https://api.access.redhat.com/support/v1/cases"
SF_SEARCH_BASE_URL = "https://api.access.redhat.com/support/search/v2/cases"


"""
Builds the HTTP headers required for Salesforce API requests.

Retrieves the bearer token from the TOKEN environment variable and
constructs the authorization and content negotiation headers used by
all Salesforce REST API calls.

Returns:
    dict:
        HTTP headers for authenticated Salesforce API requests.

Raises:
    ValueError:
        If the TOKEN environment variable is not configured.
"""


def get_sf_headers():

    token = os.getenv("TOKEN")

    if not token:
        raise ValueError("TOKEN environment variable missing")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


"""
Retrieves the primary details of a Red Hat support case.

This tool queries the Salesforce Support API for a specific case number
and returns a normalized subset of case information including summary,
status, severity, product, description, and linked external trackers.

Args:
    case_id (str):
        Red Hat support case number.

Returns:
    dict:
        Normalized case information or an error response if the case
        cannot be retrieved.
"""


@mcp.tool()
def get_support_case(case_id: str) -> Dict[str, Any]:
    """
    Fetch primary details for a specific
    Red Hat support case.
    """

    url = f"{SF_BASE_URL}/{case_id}"

    try:

        sys.stderr.write(f"[DEBUG] Fetching case: {case_id}\n")

        response = requests.get(url, headers=get_sf_headers(), timeout=15)

        sys.stderr.write(f"[DEBUG] Salesforce STATUS: " f"{response.status_code}\n")

        if response.status_code != 200:

            sys.stderr.write(f"[ERROR] Salesforce Error: " f"{response.text}\n")

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

        sys.stderr.write(f"[CRITICAL] get_support_case failed: " f"{str(e)}\n")

        return {"error": str(e)}


"""
Retrieves all technical comments associated with a Red Hat support case.

Args:
    case_number (str):
        Red Hat support case number.

Returns:
    list:
        List of technical comments returned by the Salesforce API.
        Returns an empty list if no comments are available or the
        request fails.
"""


@mcp.tool()
def list_case_comments(case_number: str) -> List[Any]:
    """
    Retrieve technical comments
    for a Red Hat support case.
    """

    url = f"{SF_BASE_URL}/{case_number}/comments"

    try:

        response = requests.get(url, headers=get_sf_headers(), timeout=15)

        sys.stderr.write(f"[DEBUG] Comments STATUS: " f"{response.status_code}\n")

        if response.status_code == 200:
            return response.json()

        sys.stderr.write(f"[ERROR] Comments Error: " f"{response.text}\n")

        return []

    except Exception as e:

        sys.stderr.write(f"[ERROR] list_case_comments failed: " f"{str(e)}\n")

        return []


"""
Retrieves updates from external trackers linked to a support case.

This includes updates from integrated engineering systems such as
Jira or Bugzilla that are associated with the specified support case.

Args:
    case_number (str):
        Red Hat support case number.

Returns:
    list:
        List of external tracker updates. Returns an empty list if no
        updates are available or the request fails.
"""


@mcp.tool()
def get_external_updates(case_number: str) -> List[Any]:
    """
    Retrieve external Jira/Bugzilla tracker
    updates linked to a support case.
    """

    url = f"{SF_BASE_URL}/" f"{case_number}/externaltrackerupdates"

    try:

        response = requests.get(url, headers=get_sf_headers(), timeout=15)

        sys.stderr.write(
            f"[DEBUG] External Tracker STATUS: " f"{response.status_code}\n"
        )

        if response.status_code == 200:
            return response.json()

        sys.stderr.write(f"[ERROR] External Tracker Error: " f"{response.text}\n")

        return []

    except Exception as e:

        sys.stderr.write(f"[ERROR] get_external_updates failed: " f"{str(e)}\n")

        return []


"""
Searches active Red Hat support cases using the v1 filter API.

This tool filters customer support cases based on predefined criteria
such as case status and SBR identifiers. It is intended for operational
case filtering rather than full-text historical investigation.

Args:
    sbrs (List[str], optional):
        List of SBR identifiers used to filter cases.

    maxResults (int):
        Maximum number of cases to return.

Returns:
    dict:
        Dictionary containing the matching support cases or an error
        response if the search fails.
"""


@mcp.tool()
def search_cases(sbrs: List[str] = None, maxResults: int = 20) -> Dict[str, Any]:
    """
    Search active Red Hat support cases.
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

        sys.stderr.write(f"[DEBUG] Search STATUS: " f"{response.status_code}\n")

        response.raise_for_status()

        data = response.json()

        return {"cases": (data if isinstance(data, list) else [data])}

    except Exception as e:

        sys.stderr.write(f"[ERROR] search_cases failed: " f"{str(e)}\n")

        return {"error": f"Search failed: {str(e)}"}


"""
Searches historical Red Hat support cases using the Search v2 API.

Performs a full-text search across historical support cases and returns
ranked search results. This tool is primarily intended for AI-assisted
investigation workflows where similar historical cases are analyzed to
identify recurring issues, common resolutions, and potential root causes.

Args:
    query (str):
        Free-text search query.

    rows (int):
        Maximum number of search results to return.

    start (int):
        Zero-based starting offset for pagination.

Returns:
    dict:
        Raw search response containing ranked historical case results.
        The Investigation Engine is responsible for transforming these
        results into lightweight Case Cards for downstream LLM analysis.
"""


import json
import sys
import requests
from typing import Dict, Any


@mcp.tool()
def search_historical_cases(
    query: str, rows: int = 5, start: int = 0
) -> Dict[str, Any]:
    """
    Search historical Red Hat support cases using the
    /support/search/v2/cases endpoint.

    Parameters
    ----------
    query : str
        Free-text search query.

    rows : int
        Number of cases to return (default: 1).

    start : int
        Zero-based offset for pagination (default: 0).
    """

    payload = {"q": query, "rows": rows, "start": start}

    try:

        sys.stderr.write(
            f"[DEBUG] Historical Search Query: '{query}' "
            f"(rows={rows}, start={start})\n"
        )

        headers = get_sf_headers()

        response = requests.post(
            SF_SEARCH_BASE_URL, headers=headers, json=payload, timeout=30
        )

        sys.stderr.write(
            f"[DEBUG] Historical Search STATUS: " f"{response.status_code}\n"
        )

        # PRINT RAW SALESFORCE/SOLR RESPONSE TO HELP DEBUG PAYLOAD ISSUES
        # sys.stderr.write(f"[DEBUG RAW SALESFORCE RESPONSE]: {response.text}\n")

        if response.status_code != 200:

            sys.stderr.write(f"[ERROR] Historical Search Error: " f"{response.text}\n")

            return {
                "error": f"Historical search failed ({response.status_code})",
                "status": response.status_code,
                "details": response.text,
                "cases": [],
            }

        data = response.json()

        # Extract Solr docs array (.response.docs)
        docs = []
        if isinstance(data, dict):
            docs = data.get("response", {}).get("docs", [])

        # sys.stderr.write(f"[DEBUG] Extracted {len(docs)} docs from Solr response.\n")

        return {
            "query": query,
            "start": start,
            "rows": rows,
            "cases": docs,
            "results": data,
        }

    except Exception as e:

        sys.stderr.write(f"[ERROR] search_historical_cases failed: " f"{str(e)}\n")

        return {"error": str(e), "cases": []}


# ------------------------------------------------
# MAIN
# ------------------------------------------------
if __name__ == "__main__":
    mcp.run()
