import json
import os

# Toggle via env or fallback
DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def log(message):
    """
    Basic debug logger (controlled via DEBUG flag)
    """
    if DEBUG:
        print(message)


def log_jira_issue(jid, jira_raw):
    """
    Logs only key Jira fields (avoids huge JSON dump)
    """
    if not DEBUG:
        return

    try:
        data = (
            json.loads(jira_raw)
            if isinstance(jira_raw, str)
            else jira_raw
        )

        fields = data.get("fields", {})

        status = fields.get("status", {}).get("name")
        summary = fields.get("summary")

        print(
            f"[DEBUG][JIRA] {jid} | status={status} | summary={summary}"
        )

    except Exception:
        print(f"[DEBUG][JIRA] {jid} | preview failed")


def log_jira_comments(jid, comments):
    """
    Logs only comment count (not full text)
    """
    if DEBUG:
        print(
            f"[DEBUG][JIRA] {jid} | comments_count={len(comments)}"
        )
