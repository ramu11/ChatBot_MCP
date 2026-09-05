"""
Main Support Orchestration Agent for Red Hat AI Support Assistant.

This module acts as the core entry point and router for processing incoming user queries.
It handles input sanitization, multi-turn request classification, context entity resolution
from session history, tool calls (Jira, Salesforce), investigation workflows, and RAG-augmented queries.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import traceback
from typing import Any, Dict, List, Optional, Union

from ai_pipeline.docs_handler import handle_docs_query
from ai_pipeline.investigation_engine import run_investigation
from ai_pipeline.request_classifier import classify_request

from llm import ask_llm
from tools.jira_adapter import (
    batch_fetch_jiras,
    build_jira_table,
    extract_jira_details,
    fetch_jira_api_data,
)
from tools.logger import log
from tools.mcp_client import get_tool_schemas
from tools.tool_router import execute_tool

# Target LLM model configuration from environment
MODEL_ID = os.getenv("MODEL_ID")

# -------------------------------------------------------------
# MCP TOOL SCHEMA PRE-CACHING (INIT)
# -------------------------------------------------------------
try:
    log("[INIT] Pre-caching MCP tool schemas...")
    get_tool_schemas("get_support_case")
except Exception as _schema_init_err:
    log(f"[WARN][INIT] MCP schema pre-caching deferred: {str(_schema_init_err)}")


# -------------------------------------------------------------
# GUARDRAIL: DATA PRIVACY CLEANER
# -------------------------------------------------------------
def sanitize_payload_data(text_or_obj: Any) -> Any:
    """
    Recursively scans and redacts sensitive data profiles (API keys, credentials, IPs, emails).
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


# -------------------------------------------------------------
# SAFE JSON LOADER
# -------------------------------------------------------------
def safe_json_loads(data: Any) -> Dict[str, Any]:
    """Safely parses JSON input payloads without raising uncaught exceptions."""
    try:
        if isinstance(data, str) and data.strip():
            return json.loads(data)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# -------------------------------------------------------------
# DYNAMIC CASE LIMIT EXTRACTION (STRICT MAX 10 CAP)
# -------------------------------------------------------------
def extract_case_limit(query: str, default: int = 5, max_cap: int = 10) -> int:
    """
    Extracts requested case counts from query (e.g. 'top 7 cases' -> 7).
    Enforces a hard limit of max_cap (10) even if user requests more (e.g. 15 -> 10).
    """
    match = re.search(r'\b(\d+)\s+cases?\b', query.lower())
    if match:
        requested = int(match.group(1))
        return min(requested, max_cap)
    return default


# -------------------------------------------------------------
# CONTEXT RESOLUTION FROM HISTORY
# -------------------------------------------------------------
def extract_entity_from_history(
    messages: List[Dict[str, str]],
) -> Dict[str, Optional[Union[str, List[str]]]]:
    """Scans prior conversation turns in reverse to locate recent entity identifiers."""
    case_pattern = r"\b(\d{8})\b"
    jira_pattern = r"\b([A-Z]{2,10}-[0-9]+)\b"

    cases_found = []
    jiras_found = []

    for msg in reversed(messages[:-1]):
        content = msg.get("content", "")

        for match in re.finditer(case_pattern, content):
            if match.group(1) not in cases_found:
                cases_found.append(match.group(1))

        for match in re.finditer(jira_pattern, content):
            if match.group(1) not in jiras_found:
                jiras_found.append(match.group(1))

    if cases_found:
        return {
            "type": "case_id",
            "value": cases_found[0],
            "all_values": cases_found[:10],
        }
    if jiras_found:
        return {
            "type": "jira_key",
            "value": jiras_found[0],
            "all_values": jiras_found[:10],
        }

    return {"type": None, "value": None, "all_values": []}


# -------------------------------------------------------------
# CASE RETRIEVAL & COMMENT PROCESSING PIPELINE
# -------------------------------------------------------------


def fetch_and_process_case(case_id: str) -> Dict[str, Any]:
    case_res = execute_tool("get_support_case", {"case_id": case_id})
    case_info = safe_json_loads(case_res)

    if not case_info or "error" in case_info:
        return {"error": f"Case {case_id} not found."}

    comments_res = execute_tool("list_case_comments", {"case_number": case_id})
    raw_comments = safe_json_loads(comments_res)

    reduced_context_raw = execute_tool(
        "extract_key_case_context",
        {
            "raw_case_data": case_info,
            "raw_comments_data": raw_comments if isinstance(raw_comments, list) else [],
        },
    )
    reduced_context = safe_json_loads(reduced_context_raw)

    # Deduplicate Jira IDs explicitly before invoking fetch
    jiras_found = extract_jira_details([case_info, raw_comments])
    unique_jira_keys = list({j["id"]: j for j in jiras_found if j.get("id")}.keys())

    # Batch fetch each unique Jira key ONCE
    jira_updates = (
        batch_fetch_jiras(unique_jira_keys, execute_tool) if unique_jira_keys else []
    )

    return {
        "case": sanitize_payload_data(reduced_context or case_info),
        "jira_updates": sanitize_payload_data(jira_updates),
    }


def fetch_case_summary_payload(case_id: str) -> Dict[str, Any]:
    """Fetches compressed metadata for a single case for parallel multi-case evaluation."""
    try:
        case_res = execute_tool("get_support_case", {"case_id": case_id})
        case_info = safe_json_loads(case_res)

        if not case_info or "error" in case_info:
            return {"case_id": case_id, "error": f"Case {case_id} not found."}

        comments_res = execute_tool("list_case_comments", {"case_number": case_id})
        raw_comments = safe_json_loads(comments_res)

        recent_comments = []
        if isinstance(raw_comments, list):
            for c in raw_comments[-3:]:
                if isinstance(c, dict) and c.get("CommentBody"):
                    recent_comments.append(c["CommentBody"][:300])

        return {
            "case_id": case_id,
            "subject": case_info.get("Subject", "No Subject"),
            "description": str(case_info.get("Description", ""))[:500],
            "status": case_info.get("Status", "Unknown"),
            "resolution": case_info.get("Resolution_Summary__c")
            or case_info.get("Closed_Reason__c")
            or "No explicit resolution provided",
            "recent_comments": recent_comments,
        }
    except Exception as err:
        return {"case_id": case_id, "error": str(err)}


def batch_fetch_cases(case_ids: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    """Fetches up to 'limit' cases (strictly max 10) in parallel using ThreadPoolExecutor."""
    results = []
    max_cases = min(limit, 10)
    unique_case_ids = list(dict.fromkeys(case_ids))[:max_cases]

    with ThreadPoolExecutor(max_workers=min(len(unique_case_ids), 10)) as executor:
        future_to_case = {
            executor.submit(fetch_case_summary_payload, cid): cid
            for cid in unique_case_ids
        }
        for future in as_completed(future_to_case):
            results.append(future.result())
    return results


# -------------------------------------------------------------
# MULTI-CASE / MULTI-JIRA RELEVANCE EVALUATORS & SYNTHESIZERS
# -------------------------------------------------------------
def summarize_and_evaluate_cases(
    query: str, cases: List[Dict[str, Any]], user_key: str, model_api: str
) -> str:
    """Evaluates case relevance against user query and synthesizes findings in one LLM call."""
    system_prompt = (
        "You are a Senior Red Hat Support Architect.\n"
        "Analyze the historical support cases provided in relation to the user's issue.\n\n"
        "Instructions:\n"
        "1. Assign a Relevance Score (HIGH, MEDIUM, LOW) to each case based on technical alignment.\n"
        "2. Provide rationale for each case.\n"
        "3. Synthesize actionable root cause and resolution findings across HIGH and MEDIUM relevance cases.\n\n"
        "Output Format:\n"
        "## Relevance Assessment\n"
        "- **Case [ID]**: [HIGH/MEDIUM/LOW] - Rationale\n\n"
        "## Multi-Case Technical Synthesis\n"
        "- **Problem Pattern**:\n"
        "- **Proven Resolutions**:\n"
        "- **Recommended Next Steps**:"
    )

    prompt = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {"user_query": query, "candidate_cases": sanitize_payload_data(cases)}
            ),
        },
    ]

    response = ask_llm(prompt, user_key, model_api)
    return response["choices"][0]["message"]["content"]


def summarize_and_evaluate_jiras(
    query: str, jiras: List[Dict[str, Any]], user_key: str, model_api: str
) -> str:
    """Evaluates technical relevance of multiple Jira tickets against user query and synthesizes findings."""
    system_prompt = (
        "You are a Senior Red Hat Engineering Architect.\n"
        "Analyze the provided Jira issues in relation to the user's inquiry.\n\n"
        "Instructions:\n"
        "1. Evaluate relevance (HIGH, MEDIUM, LOW) for each Jira ticket based on error patterns, components, and fixes.\n"
        "2. Group key findings into bug patterns, known workarounds, and target fix versions.\n"
        "3. Provide a clear recommendation or status overview.\n\n"
        "Output Format:\n"
        "## Jira Relevance Assessment\n"
        "- **[JIRA-KEY]**: [HIGH/MEDIUM/LOW] - Rationale\n\n"
        "## Technical Bug & Fix Synthesis\n"
        "- **Identified Bug Patterns**:\n"
        "- **Target Versions / Fix Status**:\n"
        "- **Recommended Workarounds**:"
    )

    prompt = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {"user_query": query, "candidate_jiras": sanitize_payload_data(jiras)}
            ),
        },
    ]

    response = ask_llm(prompt, user_key, model_api)
    return response["choices"][0]["message"]["content"]


def generate_full_summary(
    data: Dict[str, Any],
    user_key: str,
    model_api: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Synthesizes case and ticket details into an architect-level structured summary using LLM."""
    prompt = [
        {
            "role": "system",
            "content": (
                "You are a senior Red Hat support architect.\n\n"
                "Analyze the provided Case + Jira + Comments data within the context of the current ongoing conversation.\n\n"
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
        }
    ]

    if history and len(history) > 1:
        for msg in history[-5:-1]:
            prompt.append({"role": msg["role"], "content": msg["content"]})

    prompt.append({"role": "user", "content": json.dumps(data)})

    return ask_llm(prompt, user_key, model_api)["choices"][0]["message"]["content"]


# -------------------------------------------------------------
# MAIN AGENT ORCHESTRATOR
# -------------------------------------------------------------
def run_agent(
    messages: List[Dict[str, str]], user_key: str, model_api: str, token: str
) -> str:
    """Main entry point for processing incoming user messages in the Red Hat Support Agent."""
    current_message = messages[-1]["content"]
    print(f"[QUERY from run_agent in agent.py] {current_message}")

    classification = classify_request(current_message, user_key, model_api)

    request_mode = classification.get("mode", "general")
    product = classification.get("product")
    identifier = classification.get("identifier")
    confidence = classification.get("confidence", 1.0)

    # Candidate lists for multi-entity resolution
    case_ids = classification.get("case_ids", [])
    jira_ids = classification.get("jira_ids", [])

    if (
        not identifier
        and not case_ids
        and not jira_ids
        and request_mode not in ["investigation", "general"]
    ):
        historical_entity = extract_entity_from_history(messages)

        if historical_entity["type"] == "case_id":
            request_mode = "case_lookup"
            identifier = historical_entity["value"]
            case_ids = historical_entity.get("all_values", [])
            print(
                f"[CONTEXT RESOLVED] Linked case ID(s) {case_ids or identifier} from history."
            )

        elif historical_entity["type"] == "jira_key":
            request_mode = "jira_lookup"
            identifier = historical_entity["value"]
            jira_ids = historical_entity.get("all_values", [])
            print(
                f"[CONTEXT RESOLVED] Linked Jira key(s) {jira_ids or identifier} from history."
            )

    print(
        f"[CLASSIFIER from run_agent] mode={request_mode}, "
        f"product={product}, "
        f"identifier={identifier}, "
        f"case_ids={case_ids}, "
        f"jira_ids={jira_ids}, "
        f"confidence={confidence}"
    )

    # Dynamically extract case count request (capped at max 10)
    num_cases_requested = extract_case_limit(current_message, default=5, max_cap=10)

    try:
        if request_mode == "investigation":
            result = run_investigation(
                query=current_message,
                user_key=user_key,
                model_api=model_api,
                product=product or "OpenShift",
                rows=num_cases_requested,
                history=messages,
            )
            if isinstance(result, dict):
                if "error" in result:
                    return f"Investigation Error: {result['error']}"
                return result.get("summary", "No summary generated.")
            return result

        elif request_mode == "case_lookup":
            # Multi-case batch processing route
            if len(case_ids) > 1:
                log(
                    f"[BATCH] Processing {len(case_ids)} candidate historical cases in parallel..."
                )
                raw_cases = batch_fetch_cases(case_ids, limit=num_cases_requested)
                return summarize_and_evaluate_cases(
                    query=current_message,
                    cases=raw_cases,
                    user_key=user_key,
                    model_api=model_api,
                )

            # Single case fallback route
            case_id = identifier or (case_ids[0] if case_ids else None)

            if not case_id or not str(case_id).isdigit() or len(str(case_id)) != 8:
                historical_entity = extract_entity_from_history(messages)
                if historical_entity["type"] == "case_id":
                    case_id = historical_entity["value"]
                else:
                    return "Agent Exception: Missing or malformed 8-digit Salesforce Case ID."

            payload = fetch_and_process_case(case_id)
            if "error" in payload:
                return payload["error"]

            full_summary = generate_full_summary(
                payload, user_key, model_api, history=messages
            )

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(payload['jira_updates'])}"
            )

        elif request_mode == "jira_lookup":
            # Multi-Jira batch processing route
            if len(jira_ids) > 1:
                log(
                    f"[BATCH] Processing {len(jira_ids)} candidate Jira tickets in parallel..."
                )
                enriched_jiras = batch_fetch_jiras(jira_ids, execute_tool)
                clean_jiras = sanitize_payload_data(enriched_jiras)
                synthesis = summarize_and_evaluate_jiras(
                    query=current_message,
                    jiras=clean_jiras,
                    user_key=user_key,
                    model_api=model_api,
                )
                return (
                    f"{synthesis}\n\n## Jira Details\n{build_jira_table(clean_jiras)}"
                )

            # Single Jira fallback route
            jid = identifier or (jira_ids[0] if jira_ids else None)

            if not jid:
                historical_entity = extract_entity_from_history(messages)
                if historical_entity["type"] == "jira_key":
                    jid = historical_entity["value"]
                else:
                    return "Agent Exception: Missing or malformed Jira issue key."

            jira_updates = fetch_jira_api_data([{"id": jid}])
            clean_jiras = sanitize_payload_data(jira_updates)

            full_summary = generate_full_summary(
                {"jira_updates": clean_jiras}, user_key, model_api, history=messages
            )

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(clean_jiras)}"
            )

        elif request_mode == "general":
            context = ""

            if product:
                context = handle_docs_query(current_message, product)
            else:
                log(
                    "[RAG] No product detected by classifier → Skipping documentation search"
                )

            llm_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert Red Hat Technical Support Architect.\n"
                        "Maintain continuity with previous turns in the ongoing conversation."
                    ),
                }
            ]

            if len(messages) > 1:
                for msg in messages[-7:-1]:
                    llm_messages.append(
                        {"role": msg["role"], "content": msg["content"]}
                    )

            if not context or str(context).strip() in ["", "[]", "No results found"]:
                log("[RAG] No documentation context available → Using CORE_KB")
                llm_messages.append({"role": "user", "content": current_message})

                return ask_llm(
                    llm_messages,
                    user_key,
                    model_api,
                    model_id=MODEL_ID,
                    label="CORE_KB",
                    temperature=0.7,
                    max_tokens=1500,
                )["choices"][0]["message"]["content"]
            else:
                log(
                    "[RAG] Relevant documentation context found → Using LLM + RAG Enrichment"
                )
                clean_context = sanitize_payload_data(context)
                user_prompt_with_context = (
                    f"Documentation Context:\n{clean_context}\n\n"
                    f"User Question:\n{current_message}"
                )

                llm_messages.append(
                    {"role": "user", "content": user_prompt_with_context}
                )

                return ask_llm(
                    llm_messages,
                    user_key,
                    model_api,
                    model_id=MODEL_ID,
                    label="RAG_DOCS",
                    temperature=0.5,
                    max_tokens=1500,
                )["choices"][0]["message"]["content"]

    except Exception as e:
        log(
            f"[CRITICAL][AGENT] Exception in run_agent: {str(e)}\n{traceback.format_exc()}"
        )
        return f"Agent Error: {str(e)}"
