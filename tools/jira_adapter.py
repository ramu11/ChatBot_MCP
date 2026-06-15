import os
import requests

JIRA_BASE_URL = "https://redhat.atlassian.net"

EMAIL = os.getenv("EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

def _auth():
    return (EMAIL, JIRA_TOKEN)


def get_issue(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    res = requests.get(url, auth=_auth())
    res.raise_for_status()
    return res.json()


def search_issues(jql, max_results=5):
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    payload = {
        "jql": jql,
        "maxResults": max_results
    }
    res = requests.post(url, json=payload, auth=_auth())
    res.raise_for_status()
    return res.json()


def get_comments(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    res = requests.get(url, auth=_auth())
    res.raise_for_status()
    return res.json()
