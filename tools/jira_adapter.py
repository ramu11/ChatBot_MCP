import os
import requests

JIRA_BASE_URL = "https://redhat.atlassian.net"

EMAIL = os.getenv("EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")


def _auth():
    return (EMAIL, JIRA_TOKEN)


def get_issue(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    try:
        res = requests.get(url, auth=_auth())
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


def search_issues(jql, max_results=5):
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    payload = {"jql": jql, "maxResults": max_results}
    try:
        res = requests.post(url, json=payload, auth=_auth())
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP error during JQL search: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to perform JQL search: {str(e)}"}


def get_comments(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    try:
        res = requests.get(url, auth=_auth())
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
