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
        sys.stderr.write(f"DEBUG: MCP calling get_support_case for {case_id}\n")
        response = requests.get(url, headers=get_sf_headers(), timeout=15)
        
        if response.status_code != 200:
            sys.stderr.write(f"ERROR: Salesforce returned {response.status_code}\n")
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
        sys.stderr.write(f"CRITICAL ERROR: get_support_case: {str(e)}\n")
        return {"error": str(e)}

@mcp.tool()
def get_jira_details(jira_id: str) -> Dict[str, Any]:
    url = f"{JIRA_API_URL}/{jira_id}"
    headers = {"Accept": "application/json"}
    try:
        auth = get_jira_auth()
        res = requests.get(url, auth=auth, headers=headers, timeout=15)
        if res.status_code != 200:
            return {"error": f"Jira {jira_id} not accessible"}

        data = res.json()
        fields = data.get("fields", {})

        # Fetch Comments
        c_res = requests.get(f"{url}/comment?maxResults=3&orderBy=-created", auth=auth, headers=headers, timeout=10)
        comments_data = c_res.json().get("comments", []) if c_res.status_code == 200 else []
        
        recent_comments = []
        for c in comments_data:
            body = c.get("body")
            # This line uses the new flattener
            plain_text = flatten_adf(body) if isinstance(body, dict) else str(body)
            recent_comments.append({
                "author": c.get("author", {}).get("displayName", "Engineer"),
                "body": plain_text.strip()
            })

        return {
            "key": data.get("key"),
            "status": fields.get("status", {}).get("name"),
            "summary": fields.get("summary"),
            "target_version": fields.get("customfield_12345", "None Set"), 
            "recent_comments": recent_comments
        }
    except Exception as e:
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
    except Exception:
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
    except Exception:
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
        return {"cases": data if isinstance(data, list) else [data]}
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}

if __name__ == "__main__":
    mcp.run()
