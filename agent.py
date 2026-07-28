import traceback
import json
import re
import os

from llm import ask_llm
from tools.tool_router import execute_tool
from tools.logger import log, log_jira_issue, log_jira_comments
from ai_pipeline.request_classifier import classify_request
from ai_pipeline.investigation_engine import run_investigation
from ai_pipeline.docs_handler import handle_docs_query

MODEL_ID = os.getenv("MODEL_ID")


# -----------------------------
# GUARDRAIL: DATA PRIVACY CLEANER
# -----------------------------
def sanitize_payload_data(text_or_obj):
    """
    Recursively scans and replaces sensitive data profiles (API keys, tokens, IPs, emails)
    with safe masked identifiers to prevent downstream exfiltration.
    """
    if isinstance(text_or_obj, dict):
        return {k: sanitize_payload_data(v) for k, v in text_or_obj.items()}
    elif isinstance(text_or_obj, list):
        return [sanitize_payload_data(item) for item in text_or_obj]
    elif isinstance(text_or_obj, str):
        patterns = {
            "[REDACTED_EMAIL]": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "[REDACTED_BEARER_TOKEN]": r"(?i)bearer\s+[A-Za-z0-9\-\._~\+\/]+=*",
            "[REDACTED_CREDENTIAL]": r"(?i)(password|passwd|secret|api[-_]?key|token|auth)[\s:=]+[A-Za-z0-9_\-]+",
            "[REDACTED_IP]": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        }
        scrubbed = text_or_obj
        for replacement, pattern in patterns.items():
            scrubbed = re.sub(pattern, replacement, scrubbed)
        return scrubbed
    return text_or_obj


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

    jira_pattern = r"\b([A-Z]{2,10}-[0-9]+)\b"
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
            jira_raw = execute_tool("jira.get_issue", {"issue_key": jid})
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
            comments_raw = execute_tool("jira.get_comments", {"issue_key": jid})
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
                    recent_comments.append(
                        {
                            "author": c.get("author", {}).get(
                                "displayName", "Engineer"
                            ),
                            "body": body,
                        }
                    )

            # -----------------------------
            # NORMALIZE JIRA DATA
            # -----------------------------
            jira.update(
                {
                    "key": issue.get("key", jid),
                    "href": f"https://redhat.atlassian.net/browse/{issue.get('key', jid)}",
                    "status": fields.get("status", {}).get("name", "Unknown"),
                    "summary": fields.get("summary") or "No Summary",
                    "priority": fields.get("priority", {}).get("name", "None"),
                    "components": [c.get("name") for c in fields.get("components", [])],
                    "versions": [v.get("name") for v in fields.get("fixVersions", [])],
                    "recent_comments": recent_comments,
                }
            )

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
            ),
        },
        {"role": "user", "content": json.dumps(data)},
    ]

    return ask_llm(prompt, user_key, model_api)["choices"][0]["message"]["content"]


# -----------------------------
# MAIN AGENT
# -----------------------------
def run_agent(messages, user_key, model_api, token):
    query = messages[-1]["content"]
    print(f"[QUERY from run_agent in agent.py] {query}")

    classification = classify_request(query, user_key, model_api)

    request_mode = classification["mode"]
    product = classification.get("product")
    identifier = classification.get("identifier")
    confidence = classification.get("confidence", 1.0)

    print(
        f"[CLASSIFIER from run_agent] mode={request_mode}, "
        f"product={product}, "
        f"confidence={confidence}"
    )

    try:

        # ==========================================================
        # INVESTIGATION FLOW
        # ==========================================================
        if request_mode == "investigation":
            result = run_investigation(
                query=query,
                user_key=user_key,
                model_api=model_api,
                product=classification["product"],
            )
            print("######## RETURNING INVESTIGATION  from agent########")
            # If result is a dict containing a summary string, return just the text string to the UI
            if isinstance(result, dict):
                if "error" in result:
                    return f"Investigation Error: {result['error']}"
                return result.get("summary", "No summary generated.")

            return result
        # ==========================================================
        # SALESFORCE CASE FLOW
        # ==========================================================
        elif request_mode == "case_lookup":

            case_id = identifier

            # Guardrail
            if not case_id.isdigit() or len(case_id) != 8:
                return "Agent Exception: Malformed request entity rejected."

            case_res = execute_tool("get_support_case", {"case_id": case_id})

            case_info = safe_json_loads(case_res)

            if not case_info or "error" in case_info:
                return f"Case {case_id} not found."

            comments_res = execute_tool("list_case_comments", {"case_number": case_id})

            comments = safe_json_loads(comments_res)

            if isinstance(comments, list):
                comments = comments[:10]

            jiras_found = extract_jira_details([case_info, comments])

            unique = {j["id"]: j for j in jiras_found}

            jira_updates = fetch_jira_api_data(list(unique.values()))

            clean_case = sanitize_payload_data(case_info)
            clean_comments = sanitize_payload_data(comments)
            clean_jiras = sanitize_payload_data(jira_updates)

            final_data = {
                "case": clean_case,
                "case_comments": clean_comments,
                "jira_updates": clean_jiras,
            }

            full_summary = generate_full_summary(
                final_data,
                user_key,
                model_api,
            )

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(clean_jiras)}"
            )

        # ==========================================================
        # JIRA FLOW
        # ==========================================================
        elif request_mode == "jira_lookup":

            jid = identifier

            jira_updates = fetch_jira_api_data([{"id": jid}])

            clean_jiras = sanitize_payload_data(jira_updates)

            full_summary = generate_full_summary(
                {"jira_updates": clean_jiras},
                user_key,
                model_api,
            )

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(clean_jiras)}"
            )

        # ==========================================================
        # GENERAL / RAG FLOW
        # ==========================================================
        elif request_mode == "general":

            # Only search documentation if the classifier identified a product
            context = ""

            if product:
                context = handle_docs_query(query, product)
            else:
                log(
                    "[RAG] No product detected by classifier → Skipping documentation search"
                )

            # ------------------------------------------------------
            # No documentation found → use LLM knowledge
            # ------------------------------------------------------
            if not context or str(context).strip() in ["", "[]", "No results found"]:

                log("[RAG] No documentation context available → Using CORE_KB")

                prompt = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert Red Hat Technical Support Engineer.\n\n"
                            "Answer the user's question directly, clearly, and thoroughly "
                            "using your core technical expertise."
                        ),
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ]

                return ask_llm(
                    prompt,
                    user_key,
                    model_api,
                    model_id=MODEL_ID,
                    label="CORE_KB",
                    temperature=0.7,
                    max_tokens=1500,
                )["choices"][0]["message"]["content"]

            # ------------------------------------------------------
            # Documentation found → RAG-Enriched Answer
            # ------------------------------------------------------
            else:

                log(
                    "[RAG] Relevant documentation context found → Using LLM + RAG Enrichment"
                )

                clean_context = sanitize_payload_data(context)

                prompt = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert Red Hat Technical Support Architect.\n\n"
                            "INSTRUCTIONS:\n"
                            "1. Primary Directive: Answer the user's query fully and directly using your primary technical expertise.\n"
                            "2. Role of Documentation Context: Treat the provided Documentation Context strictly as optional reference material to validate, clarify, or enrich your core response.\n"
                            "3. Context Relevance: If the context is off-topic, incomplete, or conflicts with core software principles, IGNORE IT. Never allow unrelated documentation to derail or dominate the answer.\n"
                            "4. Formatting: Synthesize a clear, structured response first. Integrate relevant product specifics, version caveats, or warnings from the documentation context naturally where appropriate.\n"
                            "5. References: At the end of your response, include a brief 'Documentation References' section ONLY if specific sources from the context were directly relevant and utilized."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Documentation Context:\n{clean_context}\n\n"
                            f"User Question:\n{query}"
                        ),
                    },
                ]

                return ask_llm(
                    prompt,
                    user_key,
                    model_api,
                    model_id=MODEL_ID,
                    label="RAG_DOCS",
                    temperature=0.5,  # Raised from 0.2 to allow creative synthesis & avoid verbatim doc copying
                    max_tokens=1500,  # Increased token budget to prevent response truncation
                )["choices"][0]["message"]["content"]
    except Exception as e:
        # traceback.print_exc()
        return f"Agent Error: {str(e)}"
