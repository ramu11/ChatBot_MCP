import json
import re
from datetime import datetime, timedelta
from llm import ask_llm
from tools.tool_router import execute_tool

def extract_jira_details(data_obj):
    """
    ADVANCED JIRA DETECTOR: Captures structured metadata and performs 
    a deep scan of private comments to fetch technical context for summarization.
    """
    if not data_obj: 
        return []
    
    details = []
    jira_pattern = r'\b([A-Z]{2,10}-[0-9]+)\b'
    
    # 1. SCAN STRUCTURED OBJECTS (Prioritizing Official Tracker Data)
    items_to_scan = []
    if isinstance(data_obj, list):
        items_to_scan = data_obj
    elif isinstance(data_obj, dict):
        items_to_scan = data_obj.get("externalTrackers", []) or data_obj.get("bugzillas", [])
        if not isinstance(items_to_scan, list): items_to_scan = [items_to_scan]

    for item in items_to_scan:
        if isinstance(item, dict):
            jid = item.get("externalId") or item.get("id")
            if jid and re.match(jira_pattern, str(jid)):
                details.append({
                    "id": jid,
                    "markdown_link": f"[{jid}](https://issues.redhat.com/browse/{jid})",
                    "summary": item.get("summary") or item.get("title") or "Engineering Tracker",
                    "status": item.get("status") or item.get("statusName") or "Linked",
                    "comment_context": "" # Placeholder for deep scan
                })

    # 2. DEEP SCAN RAW TEXT (Focusing on Private Comments/Notes)
    raw_text = json.dumps(data_obj) if not isinstance(data_obj, str) else data_obj
    found_ids = set(re.findall(jira_pattern, raw_text))
    
    existing_lookup = {d["id"]: d for d in details}

    for jid in found_ids:
        # Capture 500 chars to ensure the LLM sees the full technical update/comment
        ctx_match = re.search(rf"(.{{0,500}}{jid}.{{0,500}})", raw_text, re.IGNORECASE | re.DOTALL)
        clean_ctx = ctx_match.group(1).replace("\\n", " ").strip() if ctx_match else ""
        
        if jid in existing_lookup:
            # Add the comment data to the existing official tracker
            existing_lookup[jid]["comment_context"] = clean_ctx
        else:
            # Found a new Jira ID mentioned only in comments
            details.append({
                "id": jid,
                "markdown_link": f"[{jid}](https://issues.redhat.com/browse/{jid})",
                "summary": "Mentioned in technical notes",
                "status": "Detected",
                "comment_context": clean_ctx
            })
            
    return details

def run_agent(messages, user_key, model_api, token):
    """
    The Orchestrator: Merges API data and instructs LLM to summarize private comments.
    """
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {
            "role": "system", 
            "content": (
                "You are a Red Hat Support Assistant. Summarize cases and engineering progress.\n"
                "STRICT FORMATTING:\n"
                "1. '## Case Summary': Use the case description.\n"
                "2. '## Linked Jira Progress': Create a Markdown table with columns: "
                "| Jira ID | Official Summary | Latest Progress (from Comments) | Status |.\n"
                "3. In the 'Latest Progress' column, SUMMARIZE the technical details found in the "
                "'comment_context' field of the jira_updates metadata. Focus on fix status, "
                "root cause, or engineering blockers.\n"
                "4. Use the 'markdown_link' for IDs.\n"
                "5. If no Jiras exist, state 'No engineering trackers found.'"
            )
        })

    last_msg = messages[-1]["content"]
    id_match = re.search(r"(\d{8})", last_msg)
    case_id = id_match.group(1) if id_match else None

    if case_id:
        try:
            print(f"[AGENT] Deep Scanning Case {case_id} for Comment Progress...")
            
            # A. Fetch Primary Case
            res = execute_tool("get_support_case", {"case_id": case_id})
            tool_result = json.loads(res) if isinstance(res, str) else res

            if tool_result and "error" not in str(tool_result):
                c_num = tool_result.get("caseNumber") or case_id
                
                # B. Fetch Supplemental Data
                comments_raw = execute_tool("list_case_comments", {"case_number": c_num})
                trackers_raw = execute_tool("get_external_updates", {"case_number": c_num})
                
                comments = json.loads(comments_raw) if isinstance(comments_raw, str) else (comments_raw or [])
                trackers = json.loads(trackers_raw) if isinstance(trackers_raw, str) else (trackers_raw or [])

                # C. Extract and cross-reference details
                all_found = extract_jira_details(tool_result) + \
                            extract_jira_details(comments) + \
                            extract_jira_details(trackers)
                
                # D. Merge and De-duplicate by ID (preserving comment context)
                unique_jiras = {}
                for entry in all_found:
                    jid = entry["id"]
                    if jid not in unique_jiras:
                        unique_jiras[jid] = entry
                    elif entry["comment_context"]: # Prefer the entry that has comment data
                        unique_jiras[jid]["comment_context"] = entry["comment_context"]
                
                tool_result["jira_updates"] = list(unique_jiras.values())
                tool_result["recent_technical_notes"] = (comments if isinstance(comments, list) else [])[:5]

            messages.append({"role": "user", "content": f"TOOL_DATA: {json.dumps(tool_result)}"})

        except Exception as e:
            print(f"[AGENT] Error: {str(e)}")
            messages.append({"role": "user", "content": f"Technical Error: {str(e)}"})

    # 4. Final LLM Response
    response = ask_llm(messages, user_key, model_api)
    return response["choices"][0]["message"].get("content")
