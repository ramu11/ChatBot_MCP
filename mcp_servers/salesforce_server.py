
# salesforce_server.py

import requests
import os
import sys
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


# ------------------------------------------------
# SALESFORCE AUTH
# ------------------------------------------------
def get_sf_headers():

    token = os.getenv("TOKEN")

    if not token:
        raise ValueError("TOKEN environment variable missing")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


# ------------------------------------------------
# GET SUPPORT CASE
# ------------------------------------------------
@mcp.tool()
def get_support_case(case_id: str) -> Dict[str, Any]:
    """
    Fetch primary details for a specific
    Red Hat support case.
    """

    url = f"{SF_BASE_URL}/{case_id}"

    try:

        sys.stderr.write(
            f"[DEBUG] Fetching case: {case_id}\n"
        )

        response = requests.get(
            url,
            headers=get_sf_headers(),
            timeout=15
        )

        sys.stderr.write(
            f"[DEBUG] Salesforce STATUS: "
            f"{response.status_code}\n"
        )

        if response.status_code != 200:

            sys.stderr.write(
                f"[ERROR] Salesforce Error: "
                f"{response.text}\n"
            )

            return {
                "error": f"Case {case_id} not found",
                "status": response.status_code
            }

        data = response.json()

        return {

            "caseNumber": (
                data.get("caseNumber")
                or data.get("number")
                or case_id
            ),

            "summary": (
                data.get("summary")
                or data.get("title")
                or "No Summary"
            ),

            "status": (
                data.get("status")
                or "Unknown"
            ),

            "severity": (
                data.get("severity")
                or "Normal"
            ),

            "product": (
                data.get("product")
                or "N/A"
            ),

            "description": (
                data.get("description")
                or "No description provided."
            ),

            "externalTrackers": (
                data.get("externalTrackers")
                or []
            )
        }

    except Exception as e:

        sys.stderr.write(
            f"[CRITICAL] get_support_case failed: "
            f"{str(e)}\n"
        )

        return {
            "error": str(e)
        }


# ------------------------------------------------
# LIST CASE COMMENTS
# ------------------------------------------------
@mcp.tool()
def list_case_comments(case_number: str) -> List[Any]:
    """
    Retrieve technical comments
    for a Red Hat support case.
    """

    url = f"{SF_BASE_URL}/{case_number}/comments"

    try:

        response = requests.get(
            url,
            headers=get_sf_headers(),
            timeout=15
        )

        sys.stderr.write(
            f"[DEBUG] Comments STATUS: "
            f"{response.status_code}\n"
        )

        if response.status_code == 200:
            return response.json()

        sys.stderr.write(
            f"[ERROR] Comments Error: "
            f"{response.text}\n"
        )

        return []

    except Exception as e:

        sys.stderr.write(
            f"[ERROR] list_case_comments failed: "
            f"{str(e)}\n"
        )

        return []


# ------------------------------------------------
# EXTERNAL TRACKER UPDATES
# ------------------------------------------------
@mcp.tool()
def get_external_updates(case_number: str) -> List[Any]:
    """
    Retrieve external Jira/Bugzilla tracker
    updates linked to a support case.
    """

    url = (
        f"{SF_BASE_URL}/"
        f"{case_number}/externaltrackerupdates"
    )

    try:

        response = requests.get(
            url,
            headers=get_sf_headers(),
            timeout=15
        )

        sys.stderr.write(
            f"[DEBUG] External Tracker STATUS: "
            f"{response.status_code}\n"
        )

        if response.status_code == 200:
            return response.json()

        sys.stderr.write(
            f"[ERROR] External Tracker Error: "
            f"{response.text}\n"
        )

        return []

    except Exception as e:

        sys.stderr.write(
            f"[ERROR] get_external_updates failed: "
            f"{str(e)}\n"
        )

        return []


# ------------------------------------------------
# SEARCH CASES
# ------------------------------------------------
@mcp.tool()
def search_cases(
    sbrs: List[str] = None,
    maxResults: int = 20
) -> Dict[str, Any]:
    """
    Search active Red Hat support cases.
    """

    url = f"{SF_BASE_URL}/filter"

    payload = {

        "statuses": [
            "Waiting on Red Hat",
            "Waiting on Engineering",
            "Waiting on Customer"
        ],

        "sbrs": sbrs or [],

        "maxResults": maxResults,

        "sortField": "lastModifiedDate",

        "sortOrder": "desc"
    }

    try:

        response = requests.post(
            url,
            headers=get_sf_headers(),
            json=payload,
            timeout=15
        )

        sys.stderr.write(
            f"[DEBUG] Search STATUS: "
            f"{response.status_code}\n"
        )

        response.raise_for_status()

        data = response.json()

        return {
            "cases": (
                data
                if isinstance(data, list)
                else [data]
            )
        }

    except Exception as e:

        sys.stderr.write(
            f"[ERROR] search_cases failed: "
            f"{str(e)}\n"
        )

        return {
            "error": f"Search failed: {str(e)}"
        }


# ------------------------------------------------
# MAIN
# ------------------------------------------------
if __name__ == "__main__":
    mcp.run()


