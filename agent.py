import json
import re
from llm import ask_llm
from tools.tool_router import execute_tool


# -----------------------------
# JIRA EXTRACTION
# -----------------------------
def extract_jira_details(data_obj):
    if not data_obj:
        return []

    jira_pattern = r'\b([A-Z]{2,10}-[0-9]+)\b'
    raw_text = json.dumps(data_obj) if not isinstance(data_obj, str) else data_obj
    found_ids = set(re.findall(jira_pattern, raw_text))

    return [{"id": jid} for jid in found_ids]


# -----------------------------
# JIRA ENRICHMENT
# -----------------------------
def fetch_jira_api_data(jira_list):
    enriched_results = []

    for jira in jira_list:
        jid = jira.get("id")

        try:
            jira_raw = execute_tool("get_jira_details", {"jira_id": jid})

            print(f"[DEBUG][AGENT] RAW JIRA RESPONSE for {jid}: {jira_raw}")

            api_data = json.loads(jira_raw) if isinstance(jira_raw, str) else jira_raw

            if isinstance(api_data, dict) and api_data.get("key"):

                jira.update({
                    "key": api_data.get("key"),
                    "href": api_data.get("href"),  # ✅ FIXED HERE
                    "status": api_data.get("status") or "Unknown",
                    "summary": api_data.get("summary") or "No Summary",
                    "target_version": api_data.get("target_version") or "None Set",
                    "priority": api_data.get("priority") or "None",
                    "components": api_data.get("components") or [],
                    "versions": api_data.get("versions") or [],
                    "recent_comments": api_data.get("recent_comments", [])
                })

                # 🔍 DEBUG (optional but useful)
                print(f"[DEBUG][AGENT] FINAL JIRA OBJECT: {jira}")

            else:
                print(f"[ERROR][AGENT] Invalid Jira data for {jid}: {api_data}")
                jira["status"] = "Access Restricted/Not Found"

        except Exception as e:
            print(f"[EXCEPTION][AGENT] Jira fetch failed for {jid}: {str(e)}")
            jira["status"] = "Fetch Error"

        enriched_results.append(jira)

    return enriched_results

# -----------------------------
# TABLE BUILDERS (DETERMINISTIC)
# -----------------------------
def build_jira_table(jiras):
    if not jiras:
        return "No Jira data available."

    header = (
        "| Jira | Status | Summary | Priority | Components | Versions |\n"
        "|------|--------|---------|----------|------------|----------|\n"
    )

    rows = ""

    for j in jiras:
        key = j.get("key", "N/A")
        href = j.get("href") or ""

        jira_link = f"[{key}]({href})" if href else key

        components = ", ".join(j.get("components") or []) or "None"
        versions = ", ".join(j.get("versions") or []) or "None"

        rows += (
            f"| {jira_link} "
            f"| {j.get('status') or 'Unknown'} "
            f"| {j.get('summary') or 'No Summary'} "
            f"| {j.get('priority') or 'None'} "
            f"| {components} "
            f"| {versions} |\n"
        )

    return header + rows


# -----------------------------
# COMMENTS (SUMMARY STYLE)
# -----------------------------
def build_comments(jiras, user_key=None, model_api=None):
    output = "\nEngineering Insights:\n\n"

    comments_collected = []

    for j in jiras:
        for c in j.get("recent_comments", []):
            body = c.get("body", "").strip()

            if body and len(body) > 5:
                comments_collected.append(body)

    if not comments_collected:
        return output + "No insights available.\n"

    # Combine all Jira comments
    combined_comments = "\n".join(comments_collected[:15])

    # Summarize into insights
    try:
        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize the following Jira comments into concise engineering insights. "
                    "Focus on customer concerns, engineering updates, actions, and status. "
                    "Return 3-5 bullet points only."
                )
            },
            {"role": "user", "content": combined_comments}
        ]

        summary = ask_llm(prompt, user_key, model_api)["choices"][0]["message"]["content"]

        return output + summary.strip()

    except Exception as e:
        print(f"[ERROR] Comment summarization failed: {str(e)}")

        # fallback
        fallback = "\n".join(f"- {c}" for c in comments_collected[:5])
        return output + fallback

# -----------------------------
# LLM SUMMARY ONLY
# -----------------------------
def generate_summary(data, user_key, model_api):
    prompt = [
        {"role": "system", "content": "Provide a concise technical summary."},
        {"role": "user", "content": json.dumps(data)}
    ]

    return ask_llm(prompt, user_key, model_api)["choices"][0]["message"]["content"]


# -----------------------------
# MAIN AGENT
# -----------------------------
def run_agent(messages, user_key, model_api, token):

    query = messages[-1]["content"]

    case_match = re.search(r"\b(\d{8})\b", query)
    jira_match = re.search(r"\b([A-Z]{2,10}-[0-9]+)\b", query)

    try:
        # =========================
        # LOGIC 1: CASE (TRIPLE SCAN)
        # =========================
        if case_match:
            case_id = case_match.group(1)

            case_res = execute_tool("get_support_case", {"case_id": case_id})
            case_info = json.loads(case_res) if isinstance(case_res, str) else case_res

            if not case_info or "error" in case_info:
                return f"⚠️ Case {case_id} not found."

            comments = execute_tool("list_case_comments", {"case_number": case_id})
            trackers = execute_tool("get_external_updates", {"case_number": case_id})

            comments = json.loads(comments) if isinstance(comments, str) else comments
            trackers = json.loads(trackers) if isinstance(trackers, str) else trackers

            # ✅ Triple Scan
            jiras_found = extract_jira_details([case_info, comments, trackers])
            unique = {j["id"]: j for j in jiras_found}

            jira_updates = fetch_jira_api_data(list(unique.values()))

            final_data = {
                "case": case_info,
                "jira_updates": jira_updates
            }

            summary = generate_summary(final_data, user_key, model_api)

            return (
                "## Executive Summary\n"
                f"{summary}\n\n"
                "## Engineering Details (Jira)\n"
                f"{build_jira_table(jira_updates)}\n\n"
                f"{build_comments(jira_updates, user_key, model_api)}"
            )

        # =========================
        # LOGIC 2: DIRECT JIRA
        # =========================
        elif jira_match:
            jid = jira_match.group(1)

            jira_updates = fetch_jira_api_data([{"id": jid}])

            summary = generate_summary({"jira_updates": jira_updates}, user_key, model_api)

            return (
                "## Executive Summary\n"
                f"{summary}\n\n"
                "## Engineering Details (Jira)\n"
                f"{build_jira_table(jira_updates)}\n\n"
                f"{build_comments(jira_updates, user_key, model_api)}"
            )

        # =========================
        # LOGIC 5: GENERAL QUERY
        # =========================
        else:
            return ask_llm(messages, user_key, model_api)["choices"][0]["message"]["content"]

    except Exception as e:
        return f"Agent Error: {str(e)}"
