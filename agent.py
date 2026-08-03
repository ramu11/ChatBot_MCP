# agent.py
"""
Main Support Orchestration Agent for Red Hat AI Support Assistant.

This module acts as the core entry point and router for processing incoming user queries.
It handles input sanitization, multi-turn request classification, context entity resolution
from session history, tool calls (Jira, Salesforce), investigation workflows, and RAG-augmented queries.
"""

import json
import os
import re
import traceback
from typing import Any, Dict, List, Optional, Union

from ai_pipeline.docs_handler import handle_docs_query
from ai_pipeline.investigation_engine import run_investigation
from ai_pipeline.request_classifier import classify_request
from llm import ask_llm
from tools.logger import log, log_jira_comments, log_jira_issue
from tools.mcp_client import get_tool_schemas
from tools.tool_router import execute_tool

# Target LLM model configuration from environment
MODEL_ID = os.getenv("MODEL_ID")

# -------------------------------------------------------------
# MCP TOOL SCHEMA PRE-CACHING (INIT)
# -------------------------------------------------------------
# Warm up schema cache upon module loading to avoid ListTools round-trips on tool execution
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

    Protects user and corporate privacy by replacing recognized sensitive string patterns
    with safe masked indicators before payload processing or LLM injection.

    Args:
        text_or_obj (Any): Incoming text string, list, or dictionary payload.

    Returns:
        Any: Sanitized structure with sensitive credentials redacted.
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
    """
    Safely parses JSON input payloads without raising uncaught exceptions.

    Args:
        data (Any): Input string or existing data structure.

    Returns:
        Dict[str, Any]: Parsed JSON object or empty dictionary upon failure.
    """
    try:
        if isinstance(data, str) and data.strip():
            return json.loads(data)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# -------------------------------------------------------------
# JIRA ID EXTRACTION
# -------------------------------------------------------------
def extract_jira_details(data_obj: Any) -> List[Dict[str, str]]:
    """
    Scans arbitrary data objects or text payloads to identify standard Jira ticket keys.

    Args:
        data_obj (Any): Input dictionary, list, or text payload.

    Returns:
        List[Dict[str, str]]: List of unique dictionary items containing matched Jira IDs.
    """
    if not data_obj:
        return []

    jira_pattern = r"\b([A-Z]{2,10}-[0-9]+)\b"
    raw_text = json.dumps(data_obj) if not isinstance(data_obj, str) else data_obj
    found_ids = set(re.findall(jira_pattern, raw_text))

    return [{"id": jid} for jid in found_ids]


# -------------------------------------------------------------
# CONTEXT RESOLUTION FROM HISTORY
# -------------------------------------------------------------
def extract_entity_from_history(
    messages: List[Dict[str, str]],
) -> Dict[str, Optional[str]]:
    """
    Scans prior conversation turns in reverse to locate recent entity identifiers
    (Salesforce Case IDs or Jira keys) when follow-up queries reference "that case",
    "the issue", or "fetch case details".

    Args:
        messages (List[Dict[str, str]]): List of conversation messages.

    Returns:
        Dict[str, Optional[str]]: Extracted entity info, e.g., {"type": "case_id", "value": "03795722"}
    """
    case_pattern = r"\b(\d{8})\b"
    jira_pattern = r"\b([A-Z]{2,10}-[0-9]+)\b"

    # Iterate backwards through past conversation turns
    for msg in reversed(messages[:-1]):  # Exclude current prompt
        content = msg.get("content", "")

        # 1. Search for 8-digit Salesforce Case ID
        case_match = re.search(case_pattern, content)
        if case_match:
            return {"type": "case_id", "value": case_match.group(1)}

        # 2. Search for Jira Issue Key
        jira_match = re.search(jira_pattern, content)
        if jira_match:
            return {"type": "jira_key", "value": jira_match.group(1)}

    return {"type": None, "value": None}


# -------------------------------------------------------------
# JIRA ENRICHMENT (REST API / MCP)
# -------------------------------------------------------------
def fetch_jira_api_data(jira_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Fetches issue details and recent comment history for matched Jira IDs via tool integration.

    Args:
        jira_list (List[Dict[str, str]]): List of dictionaries containing Jira ticket IDs.

    Returns:
        List[Dict[str, Any]]: Normalized list of enriched Jira issue metadata objects.
    """
    enriched_results = []

    for jira in jira_list:
        jid = jira.get("id")

        try:
            # 1. Fetch main issue metadata
            jira_raw = execute_tool("jira.get_issue", {"issue_key": jid})
            log_jira_issue(jid, jira_raw)
            issue = safe_json_loads(jira_raw)

            # Check for error dictionary (e.g. 404 or missing permissions) returned cleanly by tool router
            if not isinstance(issue, dict) or not issue:
                jira["status"] = "Invalid Jira Response"
                enriched_results.append(jira)
                continue

            if "error" in issue:
                jira["status"] = f"Not Found / {issue.get('error')}"
                jira["summary"] = f"Jira {jid} could not be retrieved"
                enriched_results.append(jira)
                continue

            fields = issue.get("fields", {})

            # 2. Fetch associated issue comments
            comments_raw = execute_tool("jira.get_comments", {"issue_key": jid})
            comments_data = safe_json_loads(comments_raw)
            comments = []

            if isinstance(comments_data, dict):
                comments = comments_data.get("comments") or []

            if not isinstance(comments, list):
                comments = []

            log_jira_comments(jid, comments)

            # 3. Restrict comment window to last 10 entries for token safety
            recent_comments = []
            for c in comments[-10:]:
                body = str(c.get("body", "")).strip()
                if body and len(body) > 20:
                    recent_comments.append(
                        {
                            "author": c.get("author", {}).get(
                                "displayName", "Engineer"
                            ),
                            "body": body,
                        }
                    )

            # 4. Standardize metadata output fields
            jira.update(
                {
                    "key": issue.get("key", jid),
                    "href": f"https://redhat.atlassian.net/browse/{issue.get('key', jid)}",
                    "status": fields.get("status", {}).get("name", "Unknown"),
                    "summary": fields.get("summary") or "No Summary",
                    "priority": fields.get("priority", {}).get("name", "None"),
                    "components": [
                        c.get("name")
                        for c in fields.get("components", [])
                        if isinstance(c, dict)
                    ],
                    "versions": [
                        v.get("name")
                        for v in fields.get("fixVersions", [])
                        if isinstance(v, dict)
                    ],
                    "recent_comments": recent_comments,
                }
            )

            log(f"[INFO][JIRA] Processed {jid}")

        except Exception as e:
            log(f"[ERROR][JIRA] {jid} fetch failed: {str(e)}")
            jira["status"] = "Fetch Error"

        enriched_results.append(jira)

    return enriched_results


# -------------------------------------------------------------
# TABLE BUILDER
# -------------------------------------------------------------
def build_jira_table(jiras: List[Dict[str, Any]]) -> str:
    """
    Formats enriched Jira metadata lists into clean Markdown tables for UI display.

    Args:
        jiras (List[Dict[str, Any]]): Enriched Jira data objects.

    Returns:
        str: Markdown-formatted table string.
    """
    if not jiras:
        return "No Jira data available."

    header = (
        "| Jira | Status | Summary | Priority | Components | Versions |\n"
        "|------|--------|---------|----------|------------|----------|\n"
    )

    rows = ""
    for j in jiras:
        key = j.get("key", j.get("id", "N/A"))
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


# -------------------------------------------------------------
# MULTI-TURN CONTEXT-AWARE SUMMARY GENERATOR
# -------------------------------------------------------------
def generate_full_summary(
    data: Dict[str, Any],
    user_key: str,
    model_api: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Synthesizes case and ticket details into an architect-level structured summary using LLM.
    Includes previous conversation turns to preserve contextual continuity during follow-up queries.

    Args:
        data (Dict[str, Any]): Combined cases, comments, and Jira data.
        user_key (str): Authentication key passed to LLM client.
        model_api (str): API endpoint target.
        history (Optional[List[Dict[str, str]]]): Prior conversation messages.

    Returns:
        str: Structured markdown executive summary text.
    """
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

    # Inject conversation context if available (limit to last 4 turns to conserve tokens)
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
    """
    Main entry point for processing incoming user messages in the Red Hat Support Agent.

    Executes classification, context-entity backfilling from history, and routes query to flow:
        - Mode 'investigation': Deep incident root-cause analysis
        - Mode 'case_lookup': Salesforce support case resolution (with historical fallback)
        - Mode 'jira_lookup': Engineering ticket details (with historical fallback)
        - Mode 'general': RAG-augmented or direct LLM general support guidance

    Args:
        messages (List[Dict[str, str]]): Conversational history matrix containing all turns.
        user_key (str): User authentication key.
        model_api (str): Target model endpoint URL.
        token (str): Service access token.

    Returns:
        str: The final agent response string generated for the frontend UI.
    """
    current_message = messages[-1]["content"]
    print(f"[QUERY from run_agent in agent.py] {current_message}")

    # 1. Step 1: Trust the Primary Classifier First
    classification = classify_request(current_message, user_key, model_api)

    request_mode = classification.get("mode", "general")
    product = classification.get("product")
    identifier = classification.get("identifier")
    confidence = classification.get("confidence", 1.0)

    # 2. Step 2: ONLY Resolve History if the Query HAS NO Explicit Identifier AND is NOT an Investigation/General search
    # If the classifier marked it as "investigation", it's a dynamic search. Do NOT attach old Jira keys or Case IDs.
    if not identifier and request_mode not in ["investigation", "general"]:
        historical_entity = extract_entity_from_history(messages)

        if historical_entity["type"] == "case_id":
            request_mode = "case_lookup"
            identifier = historical_entity["value"]
            print(f"[CONTEXT RESOLVED] Linked case ID {identifier} from history.")

        elif historical_entity["type"] == "jira_key":
            request_mode = "jira_lookup"
            identifier = historical_entity["value"]
            print(f"[CONTEXT RESOLVED] Linked Jira key {identifier} from history.")

    print(
        f"[CLASSIFIER from run_agent] mode={request_mode}, "
        f"product={product}, "
        f"identifier={identifier}, "
        f"confidence={confidence}"
    )
    try:
        # ==========================================================
        # FLOW 1: INVESTIGATION MODE
        # ==========================================================
        if request_mode == "investigation":
            result = run_investigation(
                query=current_message,
                user_key=user_key,
                model_api=model_api,
                product=product or "OpenShift",
            )
            print("######## RETURNING INVESTIGATION from agent ########")

            if isinstance(result, dict):
                if "error" in result:
                    return f"Investigation Error: {result['error']}"
                return result.get("summary", "No summary generated.")

            return result

        # ==========================================================
        # FLOW 2: SALESFORCE CASE LOOKUP MODE (Pass 2 - Deep Inspection)
        # ==========================================================
        elif request_mode == "case_lookup":
            case_id = identifier

            # Fallback check if identifier is missing or malformed
            if not case_id or not str(case_id).isdigit() or len(str(case_id)) != 8:
                historical_entity = extract_entity_from_history(messages)
                if historical_entity["type"] == "case_id":
                    case_id = historical_entity["value"]
                else:
                    return "Agent Exception: Missing or malformed 8-digit Salesforce Case ID."

            # Fetch main metadata
            case_res = execute_tool("get_support_case", {"case_id": case_id})
            case_info = safe_json_loads(case_res)

            if not case_info or "error" in case_info:
                return f"Case {case_id} not found."

            # --- TWO-PASS STRATEGY: PASS 2 DEEP INSPECTION ---
            comments_res = execute_tool("list_case_comments", {"case_number": case_id})
            raw_comments = safe_json_loads(comments_res)

            comments = []
            if isinstance(raw_comments, list):
                # 1. Filter out short automated noise/status updates
                meaningful_comments = [
                    c
                    for c in raw_comments
                    if isinstance(c, dict) and len(str(c.get("body", "")).strip()) > 20
                ]
                # 2. Tail-Windowing: Keep final 10 comments (resolution context)
                comments = meaningful_comments[-10:]

            # Cross-reference Jira details found inside case text and comments
            jiras_found = extract_jira_details([case_info, comments])
            unique = {j["id"]: j for j in jiras_found}
            jira_updates = fetch_jira_api_data(list(unique.values()))

            # Redact credentials before sending to LLM summary engine
            clean_case = sanitize_payload_data(case_info)
            clean_comments = sanitize_payload_data(comments)
            clean_jiras = sanitize_payload_data(jira_updates)

            final_data = {
                "case": clean_case,
                "case_comments": clean_comments,
                "jira_updates": clean_jiras,
            }

            full_summary = generate_full_summary(
                final_data, user_key, model_api, history=messages
            )

            return (
                f"{full_summary}\n\n"
                "## Jira Details\n"
                f"{build_jira_table(clean_jiras)}"
            )
        # ==========================================================
        # FLOW 3: JIRA ISSUE LOOKUP MODE
        # ==========================================================
        elif request_mode == "jira_lookup":
            jid = identifier

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

        # ==========================================================
        # FLOW 4: GENERAL / RAG-AUGMENTED FLOW
        # ==========================================================
        elif request_mode == "general":
            context = ""

            # Only execute RAG vector search if a product is identified
            if product:
                context = handle_docs_query(current_message, product)
            else:
                log(
                    "[RAG] No product detected by classifier → Skipping documentation search"
                )

            # Build full message prompt array including recent history
            llm_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert Red Hat Technical Support Architect.\n"
                        "Maintain continuity with previous turns in the ongoing conversation."
                    ),
                }
            ]

            # Inject up to last 6 turns of history for multi-turn conversational context
            if len(messages) > 1:
                for msg in messages[-7:-1]:
                    llm_messages.append(
                        {"role": msg["role"], "content": msg["content"]}
                    )

            # ------------------------------------------------------
            # SUB-PATH A: No context found → Core LLM Answer
            # ------------------------------------------------------
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

            # ------------------------------------------------------
            # SUB-PATH B: Context found → RAG-Enriched Core Answer
            # ------------------------------------------------------
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
        # Log stack trace and prevent runtime crashes from breaking orchestrator
        log(
            f"[CRITICAL][AGENT] Exception in run_agent: {str(e)}\n{traceback.format_exc()}"
        )
        return f"Agent Error: {str(e)}"
