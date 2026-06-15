import json
import re

from llm import ask_llm
from tools.tool_router import execute_tool
from tools.logger import log, log_jira_issue, log_jira_comments
from ai_pipeline.docs_handler import handle_docs_query


# -----------------------------
# SAFE JSON LOADER
# -----------------------------
def safe_json_loads(data):
    """
    Safely parse JSON without crashing the agent.
    Returns {} if parsing fails.
    """
    try:
        if isinstance(data, str) and data.strip():
            return json.loads(data)
        return data
    except Exception:
        return {}


# -----------------------------
# JIRA ID EXTRACTION
# -----------------------------
def extract_jira_details(data_obj):
    if not data_obj:
        return []

    jira_pattern = r'\b([A-Z]{2,10}-[0-9]+)\b'
    raw_text = json.dumps(data_obj) if not isinstance(data_obj, str) else data_obj
    found_ids = set(re.findall(jira_pattern, raw_text))

    return [{"id": jid} for jid in found_ids]


# -----------------------------
# JIRA ENRICHMENT (REST)
# -----------------------------
def fetch_jira_api_data(jira_list):

    enriched_results = []

    for jira in jira_list:

        jid = jira.get("id")

        try:
            # -----------------------------
            # FETCH ISSUE
            # -----------------------------
            jira_raw = execute_tool(
                "jira.get_issue",
                {"issue_key": jid}
            )

            log_jira_issue(jid, jira_raw)

            issue = safe_json_loads(jira_raw)

            if not isinstance(issue, dict) or not issue:
                jira["status"] = "Invalid Jira Response"
                enriched_results.append(jira)
                continue

            fields = issue.get("fields", {})

            # -----------------------------
            # FETCH COMMENTS
            # -----------------------------
            comments_raw = execute_tool(
                "jira.get_comments",
                {"issue_key": jid}
            )

            comments_data = safe_json_loads(comments_raw)

            comments = []

            if isinstance(comments_data, dict):
                comments = comments_data.get("comments") or []

            if not isinstance(comments, list):
                comments = []

            log_jira_comments(jid, comments)

            # -----------------------------
            # LIMIT COMMENTS (TOKEN SAFETY)
            # -----------------------------
            recent_comments = []

            for c in comments[-10:]:
                body = str(c.get("body", ""))

                if body and len(body) > 5:
                    recent_comments.append({
                        "author": c.get("author", {}).get("displayName", "Engineer"),
                        "body": body
                    })

            # -----------------------------
            # NORMALIZE JIRA DATA
            # -----------------------------
            jira.update({
                "key": issue.get("key", jid),
                "href": f"https://redhat.atlassian.net/browse/{issue.get('key', jid)}",
                "status": fields.get("status", {}).get("name", "Unknown"),
                "summary": fields.get("summary") or "No Summary",
                "priority": fields.get("priority", {}).get("name", "None"),
                "components": [c.get("name") for c in fields.get("components", [])],
                "versions": [v.get("name") for v in fields.get("fixVersions", [])],
                "recent_comments": recent_comments
            })

            log(f"[INFO][JIRA] Processed {jid}")

        except Exception as e:
            log(f"[ERROR][JIRA] {jid} fetch failed: {str(e)}")
            jira["status"] = "Fetch Error"

        enriched_results.append(jira)

    return enriched_results


# -----------------------------
# TABLE BUILDER
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
# SINGLE LLM SUMMARY
# -----------------------------
def generate_full_summary(data, user_key, model_api):

    prompt = [
        {
            "role": "system",
            "content": (
                "You are a senior support architect.\n\n"
                "Analyze the provided Case + Jira + Comments data.\n\n"
                "Output strictly in this format:\n\n"
                "## Executive Summary\n"
                "- Brief issue summary\n"
                "- Current status\n\n"
                "## Engineering Insights\n"
                "- Problem Pattern\n"
                "- Customer Impact\n"
                "- Engineering Analysis\n"
                "- Resolution / Next Steps\n\n"
                "Keep it concise, technical, and structured."
            )
        },
        {
            "role": "user",
            "content": json.dumps(data)
        }
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
        # CASE FLOW
        # =========================
        if case_match:

            case_id = case_match.group(1)

            case_res = execute_tool("get_support_case", {"case_id": case_id})
            case_info = safe_json_loads(case_res)

            if not case_info or "error" in case_info:
                return f"Case {case_id} not found."

            comments_res = execute_tool("list_case_comments", {"case_number": case_id})
            comments = safe_json_loads(comments_res)

            # Limit case comments to avoid token explosion
            if isinstance(comments, list):
                comments = comments[:10]

            jiras_found = extract_jira_details([case_info, comments])
            unique = {j["id"]: j for j in jiras_found}

            jira_updates = fetch_jira_api_data(list(unique.values()))

            final_data = {
                "case": case_info,
                "case_comments": comments,
                "jira_updates": jira_updates
            }

            full_summary = generate_full_summary(final_data, user_key, model_api)

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(jira_updates)}"
            )

        # =========================
        # JIRA FLOW
        # =========================
        elif jira_match:

            jid = jira_match.group(1)

            jira_updates = fetch_jira_api_data([{"id": jid}])

            full_summary = generate_full_summary(
                {"jira_updates": jira_updates},
                user_key,
                model_api
            )

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(jira_updates)}"
            )

       # =========================
        # RAG FLOW (Inside agent.py)
        # =========================
        else:
            # 1. This invokes your keyword matching check & vector lookup
            context = handle_docs_query(query)

            # 2. Safe verification logic handles both missing strings or empty results
            if not context or str(context).strip() in ["", "[]", "No results found"]:
                log("[RAG] No relevant documentation found or product skipped → Defaulting to LLM core knowledge base")
                
                # Isolated prompt layout avoids dragging bloated historical conversation matrices
                prompt = [
                    {"role": "system", "content": "You are a Red Hat Technical Support Engineer. Answer clearly and concisely using your internal technical expertise."},
                    {"role": "user", "content": query}
                ]
                
                return ask_llm(prompt, user_key, model_api, model_id="gemini-2.5-flash", label="CORE_KB")["choices"][0]["message"]["content"]

            else:
                log("[RAG] Context discovered → Constructing fully grounded technical response")
                #print("\n" + "="*50 + "\n[DEBUG RAG] WHAT IS IN THE RETRIEVED CONTEXT VARIABLE?\n" + str(context) + "\n" + "="*50 + "\n")
                
                # REVISED SYSTEM PROMPT: Permits safe engineering knowledge fallback if docs reference older manuals
                prompt = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert Red Hat Technical Support Engineer.\n"
                            "Answer the user query using the provided documentation context.\n\n"
                            
                            "CRITICAL INSTRUCTION FOR REFS:\n"
                            "If the provided context states that a migration procedure must follow an older version sequence "
                            "(such as the Streams for Apache Kafka 2.9.x documentation), summarize that version path constraint first, "
                            "and then seamlessly provide the exact, expected technical steps, commands, and configurations "
                            "needed to accomplish that migration sequence based on your internal technical engineering expertise.\n\n"
                            
                            "Dynamically adjust your format based on the query type:\n\n"
                            "--- TYPE A: Concept explanation ---\n"
                            "1. 1-2 sentence direct definition.\n"
                            "2. 3-4 short, punchy bullet points highlighting key mechanics.\n\n"
                            "--- TYPE B: Technical procedures / Migrations ---\n"
                            "1. Start with a 1-sentence path overview referencing the version required (e.g., from the context).\n"
                            "2. Provide the clear, sequential step-by-step procedure using numbered bullet points.\n"
                            "3. Include actual configuration parameters (e.g., migration tokens, controller quorum definitions) and shell execution scripts.\n\n"
                            "Always provide a source line referencing the context documentation at the very bottom."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Context:\n{context}\n\nQuestion:\n{query}"
                    }
                ]

                return ask_llm(
                    prompt, 
                    user_key, 
                    model_api, 
                    model_id="gemini-2.5-flash", 
                    label="RAG_DOCS",
                    temperature=0.2,             # Slightly raised to allow fluid command generation
                    max_tokens=800               
                )["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Agent Error: {str(e)}"
