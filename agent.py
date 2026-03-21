import json
import re
from datetime import datetime, timedelta
from llm import ask_llm
from tools.tool_router import execute_tool

def run_agent(messages, user_key, model_api, token):
    # 1. Initialize System Instructions if not present
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {
            "role": "system",
            "content": (
                "You are a Red Hat Support Assistant. Summarize cases and Jira progress.\n"
                "CRITICAL RULES:\n"
                "- Only show cases that match the user's requested SBR (e.g., Messaging).\n"
                "- List cases in the order provided (Latest/Newest first).\n"
                "- For Jiras, state: **Status**, **Target Release**, and **Progress**.\n"
                "- Use clickable Markdown links: [Jira ID](https://issues.redhat.com/browse/ID)."
            )
        })

    last_user_msg = messages[-1]["content"].lower()
    
    # ID Detection (8-digit Case ID)
    id_match = re.search(r"(\d{8})", last_user_msg)
    case_id = id_match.group(1) if id_match else None
    
    # Filter/Search Detection
    is_mcp_filter = any(kw in last_user_msg for kw in ["search", "filter", "find", "cases", "list", "monitor"])

    tool_to_call = None
    tool_args = {}

    # Logic for Single Case Deep Scan
    if case_id:
        tool_to_call = "get_support_case"
        tool_args = {"case_id": case_id}
    
    # Logic for Keyword/SBR Search
    elif is_mcp_filter:
        tool_to_call = "search_cases"
        now = datetime.utcnow()
        start_dt = now - timedelta(days=180)
        
        # ACTIVE STATUSES ONLY
        active_statuses = ["Waiting on Red Hat", "Waiting on Customer", "Waiting on Engineering"]
        
        # STRICT SBR DETECTION (Ensures 'Messaging' focus)
        requested_sbrs = []
        if "messaging" in last_user_msg:
            requested_sbrs = ["Messaging"]
        elif "rhoai" in last_user_msg:
            requested_sbrs = ["RHOAI"]
            
        tool_args = {
            "keyword": "", 
            "statuses": active_statuses,
            "sbrs": requested_sbrs,
            "includeClosed": False,
            "startDate": start_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            "endDate": now.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            "maxResults": 50
        }

    if tool_to_call:
        try:
            # UNIVERSAL JIRA EXTRACTOR (Captures SRVKP, AAP, AMQ, OCP, etc.)
            def extract_jira_details(data_obj):
                jira_pattern = r'\b([A-Z]{2,10}-[0-9]+)\b'
                raw_text = json.dumps(data_obj)
                found_ids = sorted(list(set(re.findall(jira_pattern, raw_text))))
                details = []
                for jid in found_ids:
                    # Capture context around the ID for Status/Target hints
                    ctx = re.search(rf"(.{{0,50}}{jid}.{{0,50}})", raw_text, re.IGNORECASE | re.DOTALL)
                    clean_ctx = ctx.group(1).replace("\\n", " ").strip() if ctx else "Mentioned in case."
                    
                    details.append({
                        "id": jid, 
                        "url": f"https://issues.redhat.com/browse/{jid}", 
                        "context": clean_ctx
                    })
                return details

            # Call the primary tool (Router handles the bridge to the Server)
            primary_output = execute_tool(tool_to_call, tool_args)
            tool_result = json.loads(primary_output) if isinstance(primary_output, str) else primary_output

            # DEEP SCAN: If fetching a specific case, look at comments and trackers
            if tool_to_call == "get_support_case" and "error" not in tool_result:
                c_num = tool_result.get("case_id")
                comments = execute_tool("list_case_comments", {"case_number": c_num})
                trackers = execute_tool("get_external_updates", {"case_number": c_num})
                
                # Combine Jira findings from all three sources
                all_jiras = extract_jira_details(tool_result) + extract_jira_details(comments) + extract_jira_details(trackers)
                
                # De-duplicate Jiras by ID
                unique_jiras = {j["id"]: j for j in all_jiras}
                tool_result["jira_updates"] = list(unique_jiras.values())
                
                # Include the latest technical comment for the LLM to summarize
                if isinstance(comments, list) and len(comments) > 0:
                    tool_result["latest_tech_update"] = comments[0].get("text", "")[:600]

            # Feedback to LLM
            messages.append({"role": "user", "content": f"Tool Result (Latest First): {json.dumps(tool_result)}"})
            
        except Exception as e:
            messages.append({"role": "user", "content": f"Internal Agent Error: {str(e)}"})

    # Final call to LLM for professional summary
    response_data = ask_llm(messages, user_key, model_api)
    return response_data["choices"][0]["message"].get("content")
