import json
import re
from datetime import datetime
from llm import ask_llm
from tools.tool_router import execute_tool

def extract_jira_details(data_obj):
    """
    Deep scans the entire object for Jira IDs and captures 300 chars of 
    surrounding text for Executive Summary context.
    """
    if not data_obj: return []
    details = []
    jira_pattern = r'\b([A-Z]{2,10}-[0-9]+)\b'
    
    # Convert object to string to scan everything at once
    raw_text = json.dumps(data_obj) if not isinstance(data_obj, str) else data_obj
    found_ids = set(re.findall(jira_pattern, raw_text))

    for jid in found_ids:
        # Capture context around the ID
        ctx_match = re.search(rf"(.{{0,300}}{jid}.{{0,300}})", raw_text, re.IGNORECASE | re.DOTALL)
        clean_ctx = ctx_match.group(1).replace("\\n", " ").strip() if ctx_match else ""
        
        details.append({
            "id": jid,
            "markdown_link": f'<a href="https://issues.redhat.com/browse/{jid}">{jid}</a>',
            "summary": "Engineering Tracker Found",
            "status": "Detected",
            "comment_context": clean_ctx
        })
            
    return details

def fetch_jira_api_data(jira_list):
    """Enriches IDs by calling get_jira_details tool."""
    enriched_results = []
    for jira in jira_list:
        jid = jira.get("id")
        try:
            jira_raw = execute_tool("get_jira_details", {"jira_id": jid})
            api_data = json.loads(jira_raw) if isinstance(jira_raw, str) else jira_raw
            
            if api_data and "error" not in str(api_data):
                jira.update({
                    "status": api_data.get("status", jira.get("status")),
                    "summary": api_data.get("summary", jira.get("summary")),
                    "target_version": api_data.get("target_version", "None Set"),
                    "api_comments": api_data.get("recent_comments", [])
                })
            else:
                jira["status"] = "Access Restricted/Not Found"
        except Exception:
            jira["status"] = "Fetch Error"
        
        enriched_results.append(jira)
    return enriched_results

def run_agent(messages, user_key, model_api, token):
    # 1. THE RIGID TEMPLATE
    system_instr = (
        "You are a Red Hat Support Assistant. If 'DATA_FOUND' is present, you MUST "
        "ignore your standard training and use this EXACT Markdown format:\n\n"
        "## Executive Summary\n"
        "(Write a high-level technical paragraph here based on the description and comments)\n\n"
        "## Engineering Progress (Jira)\n"
        "| Key | Status | Summary | Target Version |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "(Fill this table using jira_updates. Use the 'markdown_link' field for the Key column)\n\n"
        "### 💬 Recent Engineering Comments\n"
        "(List exactly the comments from recent_comments as 'Author: Comment')\n\n"
        "STRICT RULE: Do not include 'Subject', 'Status', or 'Severity' lists at the top. "
        "Do not stop until the table is complete."
    )

    if not messages or (isinstance(messages, list) and messages[0].get("role") != "system"):
        messages.insert(0, {"role": "system", "content": system_instr})

    query = messages[-1]["content"]
    case_match = re.search(r"\b(\d{8})\b", query)
    jira_match = re.search(r"\b([A-Z]{2,10}-[0-9]+)\b", query)
    final_data = {}

    try:
        if case_match:
            case_id = case_match.group(1)
            print(f"[AGENT] Fetching Case: {case_id}")
            
            case_res = execute_tool("get_support_case", {"case_id": case_id})
            case_info = json.loads(case_res) if isinstance(case_res, str) else case_res
            
            if case_info and isinstance(case_info, dict) and "error" not in case_info:
                # Truncate long descriptions to keep the LLM focused
                if "description" in case_info:
                    case_info["description"] = case_info["description"][:1200] + "..."
                
                final_data = case_info 
                c_num = case_info.get("caseNumber") or case_id
                
                # Fetch Supplemental Data
                try:
                    comments = json.loads(execute_tool("list_case_comments", {"case_number": c_num}))
                    trackers = json.loads(execute_tool("get_external_updates", {"case_number": c_num}))
                except:
                    comments, trackers = [], []

                # Find Jiras and get live API data
                jiras_found = extract_jira_details([case_info, comments, trackers])
                unique_jiras = {j["id"]: j for j in jiras_found}
                
                final_data["recent_comments"] = (comments if isinstance(comments, list) else [])[:5]
                final_data["jira_updates"] = fetch_jira_api_data(list(unique_jiras.values()))
            else:
                return f"### ⚠️ Salesforce Error\nCould not find Case {case_id}."

        elif jira_match:
            jid = jira_match.group(1)
            placeholder = [{"id": jid, "markdown_link": f"[{jid}](https://issues.redhat.com/browse/{jid})"}]
            final_data["jira_updates"] = fetch_jira_api_data(placeholder)

        # 2. THE FINAL HANDOFF
        if final_data:
            messages.append({
                "role": "system", 
                "content": f"DATA_FOUND: {json.dumps(final_data)}"
            })
            messages.append({
                "role": "user", 
                "content": "Generate the Executive Summary and Engineering Table now."
            })

    except Exception as e:
        return f"Agent Error: {str(e)}"

    return ask_llm(messages, user_key, model_api)["choices"][0]["message"].get("content")
