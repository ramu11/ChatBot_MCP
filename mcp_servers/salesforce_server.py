import requests
import os
import sys
from typing import List, Optional, Union
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("redhat-support-server")

# Your working Base URL for Red Hat Case API
BASE_URL = "https://api.access.redhat.com/support/v1/cases"

def get_headers():
    """Helper to get authentication headers from environment variables."""
    token = os.getenv("TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

@mcp.tool()
def get_support_case(case_id: str):
    """Fetch details for a specific 8-digit Red Hat support case by ID."""
    url = f"{BASE_URL}/{case_id}"
    try:
        sys.stderr.write(f"DEBUG: Fetching case {case_id}\n")
        response = requests.get(url, headers=get_headers(), timeout=15)
        
        if response.status_code != 200:
            return {"error": f"Failed to fetch case {case_id}", "status": response.status_code}
            
        data = response.json()
        # Return a cleaned object for the Agent to process
        return {
            "case_id": case_id,
            "summary": data.get("caseSummary") or data.get("summary"),
            "status": data.get("status"),
            "sbr": data.get("sbr"),
            "severity": data.get("severity"),
            "full_data": data
        }
    except Exception as e:
        return {"error": f"Connection failed: {str(e)}"}

@mcp.tool()
def search_cases(
    keyword: Optional[str] = "",
    statuses: Optional[list] = None, 
    sbrs: Optional[list] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    maxResults: int = 50,
    includeClosed: bool = False
):
    """
    Search active Red Hat cases. 
    Enforces 'Waiting' statuses and sorts by Latest Modified first.
    """
    url = f"{BASE_URL}/filter"
    
    # STRICT DEFAULT: Only pull cases waiting for action (excludes Closed/Resolved)
    active_only = ["Waiting on Red Hat", "Waiting on Customer", "Waiting on Engineering"]
    
    payload = {
        "keyword": keyword if keyword else "",
        "statuses": statuses if statuses else active_only,
        "sbrs": sbrs if sbrs else [],
        "maxResults": maxResults,
        "includeClosed": includeClosed, 
        "startDate": startDate,
        "endDate": endDate,
        "sortField": "lastModifiedDate", # Crucial for 'Latest First' requirement
        "sortOrder": "desc"             # Newest updates at the top
    }
    
    # Remove None values to keep the API happy
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        sys.stderr.write(f"DEBUG: Search payload: {payload}\n")
        response = requests.post(url, headers=get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        # Consistent format: Always return a dict with a 'cases' list
        if isinstance(data, list):
            return {"cases": data, "count": len(data)}
        return data 
        
    except Exception as e:
        return {"error": "Search failed", "details": str(e)}

@mcp.tool()
def list_case_comments(case_number: str):
    """Retrieve full history of comments. Used for Deep Scan to find Jira progress."""
    url = f"{BASE_URL}/{case_number}/comments"
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Comments fetch failed: {str(e)}"}

@mcp.tool()
def get_external_updates(case_number: str):
    """Retrieve official Jira/Bugzilla sync data (Status & Target Releases)."""
    url = f"{BASE_URL}/{case_number}/externaltrackerupdates"
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Tracker fetch failed: {str(e)}"}

if __name__ == "__main__":
    # Runs the MCP server logic
    mcp.run()
