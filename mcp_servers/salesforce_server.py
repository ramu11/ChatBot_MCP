import requests
import os
import sys
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("redhat-support-server")

# The authenticated Red Hat Case API endpoint
BASE_URL = "https://api.access.redhat.com/support/v1/cases"

def get_headers():
    """Helper to pull the Red Hat API Token from the environment."""
    token = os.getenv("TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

@mcp.tool()
def get_support_case(case_id: str) -> Dict[str, Any]:
    """
    Fetch primary details for a specific 8-digit Red Hat support case.
    Captures core fields and structured external trackers for Jira detection.
    """
    url = f"{BASE_URL}/{case_id}"
    try:
        sys.stderr.write(f"DEBUG: MCP calling get_support_case for {case_id}\n")
        response = requests.get(url, headers=get_headers(), timeout=15)
        
        if response.status_code != 200:
            return {"error": "NotFound", "status": response.status_code}
            
        data = response.json()
        sys.stderr.write(f"DEBUG: API returned keys: {list(data.keys())}\n")
        
        # UNIVERSAL MAPPER: Standardizing the response for the Agent
        return {
            "caseNumber": data.get("caseNumber") or data.get("number") or case_id,
            "summary": data.get("summary") or data.get("caseSummary") or data.get("title") or "No Summary",
            "status": data.get("status") or data.get("state") or "Unknown",
            "severity": data.get("severity") or data.get("priority") or "Normal",
            "product": data.get("product") or data.get("service") or "N/A",
            "description": data.get("description") or data.get("details") or "No description provided.",
            # Include structured trackers if they exist in the header
            "externalTrackers": data.get("externalTrackers") or data.get("bugzillas") or []
        }
    except Exception as e:
        sys.stderr.write(f"ERROR: get_support_case failed: {str(e)}\n")
        return {"error": str(e)}

@mcp.tool()
def search_cases(sbrs: List[str] = None, maxResults: int = 20) -> Dict[str, Any]:
    """
    Search active Red Hat cases based on SBR or status via the filter endpoint.
    """
    url = f"{BASE_URL}/filter"
    payload = {
        "statuses": ["Waiting on Red Hat", "Waiting on Engineering", "Waiting on Customer"],
        "sbrs": sbrs or [],
        "maxResults": maxResults,
        "sortField": "lastModifiedDate",
        "sortOrder": "desc"
    }
    
    try:
        sys.stderr.write(f"DEBUG: MCP calling search_cases for SBRs: {sbrs}\n")
        res = requests.post(url, headers=get_headers(), json=payload, timeout=15)
        res.raise_for_status()
        
        data = res.json()
        return {"cases": data if isinstance(data, list) else [data]}
    except Exception as e:
        sys.stderr.write(f"ERROR: search_cases failed: {str(e)}\n")
        return {"error": f"Case search failed: {str(e)}"}

@mcp.tool()
def list_case_comments(case_number: str) -> List[Any]:
    """
    Retrieve history of technical comments. 
    Returns raw list to allow Agent's Regex to scan for hidden Jiras.
    """
    url = f"{BASE_URL}/{case_number}/comments"
    try:
        sys.stderr.write(f"DEBUG: MCP fetching comments for {case_number}\n")
        res = requests.get(url, headers=get_headers(), timeout=15)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        sys.stderr.write(f"WARNING: Comment fetch failed: {str(e)}\n")
        return []

@mcp.tool()
def get_external_updates(case_number: str) -> List[Any]:
    """
    Retrieve official Jira/Bugzilla sync data (External Trackers).
    Essential for the Triple-Scan logic.
    """
    url = f"{BASE_URL}/{case_number}/externaltrackerupdates"
    try:
        sys.stderr.write(f"DEBUG: MCP fetching tracker updates for {case_number}\n")
        res = requests.get(url, headers=get_headers(), timeout=15)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        sys.stderr.write(f"WARNING: Tracker fetch failed: {str(e)}\n")
        return []

if __name__ == "__main__":
    # Required for the stdio_client in mcp_client.py
    mcp.run()
