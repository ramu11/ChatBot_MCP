import requests
import os
import re
from typing import List, Optional, Union
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("redhat-support-server")

BASE_URL = "https://api.access.redhat.com/support/v1/cases"

def get_headers():
    """Helper to get authentication headers from environment."""
    token = os.getenv("TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

@mcp.tool()
def get_support_case(case_id: str):
    """
    Fetch details for a specific Red Hat support case by ID.
    Returns case details and full data for deep Jira scanning in agent.py.
    """
    url = f"{BASE_URL}/{case_id}"
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        
        if response.status_code != 200:
            return {"error": f"Failed to fetch case {case_id}", "status": response.status_code}

        data = response.json()
        
        # We return the core fields + the full 'data' object.
        # This allows agent.py to scan every single field for Jira IDs like RHOAIRFE-730.
        return {
            "case_id": case_id,
            "summary": data.get("caseSummary"),
            "status": data.get("status"),
            "severity": data.get("severity"),
            "automation_enabled": data.get("caseAutomationEnabled"),
            "full_data": data  # The deep-scan logic in agent.py needs this
        }
    except Exception as e:
        return {"error": f"Connection failed: {str(e)}"}

@mcp.tool()
def search_cases(keyword: str = "", statuses: list = None, sbrs: list = None):
    """
    Search for Red Hat cases using filters.
    Default status: ['Waiting on Red Hat']
    Default SBRs: ['FuseSource', 'Messaging', 'JBoss Security', 'RHOAI', 'RHEL AI']
    """
    url = f"{BASE_URL}/filter"
    
    # Define defaults per your requirements
    default_statuses = ["Waiting on Red Hat"]
    default_sbrs = ["FuseSource", "Messaging", "JBoss Security", "RHOAI", "RHEL AI"]

    payload = {
        "keyword": keyword,
        "statuses": statuses if statuses else default_statuses,
        "sbrs": sbrs if sbrs else default_sbrs,
        "maxResults": 10,
        "includeClosed": False
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        
        # The filter endpoint returns a list of cases. 
        # agent.py will now scan each item in this list for Jira links.
        return response.json()
        
    except Exception as e:
        # Provide detailed error info for debugging
        error_detail = getattr(e.response, 'text', str(e))
        return {"error": f"Search failed", "details": error_detail}

if __name__ == "__main__":
    # Start the MCP stdio server
    mcp.run()

