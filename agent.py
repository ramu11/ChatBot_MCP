# agent.py — Orchestrates LLM + MCP tool calls

import json
import re
from llm import ask_llm
from tools.tool_router import execute_tool

def run_agent(messages, user_key, model_api, token):
    """
    Handles three logic flows:
    1. Generic Search: No tool call, just LLM.
    2. MCP Case ID: Specific 8-digit search.
    3. MCP Filter: Search for Jiras/Messaging cases.
    """

    # STEP 0 — Initialize System Instruction
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {
            "role": "system",
            "content": (
                "You are a helpful Red Hat Support Assistant. "
                "Format answers using short paragraphs and bullet points. "
                "If tool results contain 'jira_links', you MUST list each one as a clickable Markdown link. "
                "Example: [Link Jira (RHOAIRFE-730)](https://issues.redhat.com)"
            )
        })

    # STEP 1 — Logic Detection
    last_user_msg = messages[-1]["content"].lower()
    
    # 1a. Detection for MCP: 8-digit Case ID
    id_match = re.search(r"(\d{8})", last_user_msg)
    case_id = id_match.group(1) if id_match else None

    # 1b. Detection for MCP: Filter Search
    mcp_filter_keywords = ["search", "filter", "find cases", "monitor"]
    is_mcp_filter = any(kw in last_user_msg for kw in mcp_filter_keywords)

    tool_to_call = None
    tool_args = {}

    if case_id:
        # FLOW 2a: Search by Case ID
        tool_to_call = "get_support_case"
        tool_args = {"case_id": case_id}
    elif is_mcp_filter:
        # FLOW 2b: Filter Search
        tool_to_call = "search_cases"
        
        clean_kw = last_user_msg
        for kw in ["search", "filter", "find", "cases"]:
            clean_kw = clean_kw.replace(kw, "")
        
        available_sbrs = ["FuseSource", "Messaging", "JBoss Security", "RHOAI", "RHEL AI"]
        matched_sbrs = [sbr for sbr in available_sbrs if sbr.lower() in last_user_msg]

        tool_args = {
            "keyword": clean_kw.strip(),
            "statuses": ["Waiting on Red Hat"],
            "sbrs": matched_sbrs if matched_sbrs else available_sbrs
        }

    # STEP 2 — Execute MCP Tool and Process Results
    if tool_to_call:
        try:
            tool_output = execute_tool(tool_to_call, tool_args)
            
            # Standardize tool output to dict
            if isinstance(tool_output, str):
                try:
                    tool_result = json.loads(tool_output)
                except json.JSONDecodeError:
                    tool_result = {"result": tool_output}
            else:
                tool_result = tool_output

            # Helper: Extract ALL Jira IDs matching your specific project codes
            def get_jira_links(data_obj):
                # Regex for your specific project codes
                jira_pattern = r'\b(RHOAIRFE|ENTMQST|ENTMQBR|DBZ|QUARKUS)-[0-9]+\b'
                # Convert object to string to scan all fields (deep scan)
                raw_text = json.dumps(data_obj)
                found_ids = sorted(list(set(re.findall(jira_pattern, raw_text))))
                
                links = []
                for jid in found_ids:
                    links.append({
                        "id": jid, 
                        "url": f"https://issues.redhat.com{jid}"
                    })
                return links

            # Process single case results
            jira_info = get_jira_links(tool_result)
            if jira_info:
                tool_result["jira_links"] = jira_info
                # Keep jira_url for backward compatibility
                tool_result["jira_url"] = jira_info[0]["url"]

            # Process list of cases (from search_cases)
            # The API usually returns a list under 'cases' or 'results'
            case_list = tool_result.get("cases", []) or tool_result.get("results", [])
            if isinstance(case_list, list):
                for case in case_list:
                    c_jira_info = get_jira_links(case)
                    if c_jira_info:
                        case["jira_links"] = c_jira_info
                        case["jira_url"] = c_jira_info[0]["url"]

            tool_result_str = json.dumps(tool_result, separators=(",", ":"))
            messages.append({
                "role": "user",
                "content": f"MCP Tool Result ({tool_to_call}):\n{tool_result_str}"
            })

        except Exception as e:
            messages.append({"role": "user", "content": f"MCP Tool Error: {str(e)}"})

    # STEP 3 — LLM Final Response
    response = ask_llm(messages, user_key, model_api)
    
    try:
        msg_content = response["choices"][0]["message"].get("content", "")
    except (KeyError, IndexError, TypeError):
        try:
            msg_content = response["choices"]["message"].get("content", "")
        except:
            msg_content = "I'm sorry, I couldn't process that request."

    return msg_content

