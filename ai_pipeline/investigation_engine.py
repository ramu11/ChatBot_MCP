# investigation_engine.py
"""
Investigation Engine Module for Red Hat Support AI Assistant.

Executes incident investigation workflows by fetching raw historical support cases,
performing date and status filtering locally in Python, and synthesizing
findings via LLM.
"""

from datetime import datetime
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set

from ai_pipeline.keywords import (
    clean_query_for_search,
    extract_date_filter,
    extract_status_filter,
    extract_product,
    CASE_STATUS_MAP,
    PRODUCT_CATALOG,
    INVESTIGATION_KEYWORDS,
)
from llm import ask_llm, generate_pass1_summary
from tools.tool_router import execute_tool

USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")
MODEL_ID = os.getenv("MODEL_ID")


def sanitize_payload_data(text_or_obj: Any) -> Any:
    """Recursively redacts sensitive patterns in case payloads prior to LLM submission."""
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


def is_followup_summarization(query: str) -> bool:
    """Detects if the user submitted a follow-up summarization request for retrieved cases."""
    if not query:
        return False

    q = query.lower().strip()
    summary_intent_terms = [
        kw for kw in INVESTIGATION_KEYWORDS
        if any(term in kw for term in ["summary", "summarize", "pattern", "trend", "root cause"])
    ]
    summary_intent_terms.extend(["summarize", "summary", "above cases", "these cases", "results", "findings"])

    has_summary_intent = any(term in q for term in summary_intent_terms)
    has_search_verb = any(v in q for v in ["search", "list", "find", "get", "show"])

    return has_summary_intent and not has_search_verb


def filter_cases_by_status_and_date(
    cases: List[Dict[str, Any]],
    query: str,
    date_filter: dict
) -> List[Dict[str, Any]]:
    """Applies Python-level filtering for both Status and Date criteria."""
    if not cases:
        return []

    q = query.lower()
    filtered_cases = []

    # 1. PARSE SPECIFIC TARGET STATUSES FROM QUERY
    target_statuses: Set[str] = set()
    for exact_status, phrases in CASE_STATUS_MAP.items():
        for phrase in phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", q):
                target_statuses.add(exact_status.lower())

    # Detect general open/pending/active intent
    is_general_pending = bool(
        re.search(r"\b(waiting|open|active|unresolved|pending|long\s+running)\b", q)
    )

    # 2. PARSE EXPECTED DATE BOUNDS
    target_dt = None
    date_field = date_filter.get("field", "CreatedDate") if date_filter else "CreatedDate"
    if date_filter and "value" in date_filter:
        try:
            target_str = date_filter["value"].replace("Z", "+00:00")
            target_dt = datetime.fromisoformat(target_str)
        except Exception:
            target_dt = None

    # 3. EVALUATE EACH CASE
    for case in cases:
        # Debug schema keys on the first item
        if cases.index(case) == 0:
            sys.stderr.write(f"[DEBUG SOLR SCHEMA KEYS]: {list(case.keys())}\n")
            sys.stderr.write(f"[DEBUG SAMPLE STATUS]: {case.get('case_internal_status')} / {case.get('status')}\n")
            sys.stderr.write(f"[DEBUG SAMPLE DATE]: {case.get('case_createdDate')} / {case.get('createdDate')}\n")

        # Extract case status across potential backend field variants
        case_status = str(
            case.get("case_internal_status")
            or case.get("status")
            or case.get("Status")
            or ""
        ).strip().lower()

        # --- STATUS CHECK ---
        if target_statuses:
            # If explicit status mapped, match substring
            if not any(ts in case_status for ts in target_statuses):
                continue
        elif is_general_pending:
            # Exclude closed/resolved variants using substring matching
            if any(term in case_status for term in ["closed", "resolved", "completed", "cancelled", "canceled"]):
                continue

        # --- DATE CHECK ---
        if target_dt:
            raw_date = (
                case.get("case_createdDate")
                or case.get(date_field)
                or case.get("createdDate")
                or case.get("created_date")
                or case.get("createdDate_dt")
                or case.get("CreatedDate")
            )
            if raw_date:
                try:
                    clean_date = str(raw_date).replace("Z", "+00:00")
                    case_dt = datetime.fromisoformat(clean_date)

                    operator = date_filter.get("operator", "<=")
                    if operator in ["<=", "<"] and case_dt > target_dt:
                        continue
                    elif operator in [">=", ">"] and case_dt < target_dt:
                        continue
                except Exception:
                    pass

        filtered_cases.append(case)

    return filtered_cases

def _generate_investigation_summary(
    query: str,
    cases: List[Dict[str, Any]],
    user_key: str,
    model_api: str,
) -> str:
    """Delegates Pass 1 formatting to llm.generate_pass1_summary."""
    if not cases:
        return "No historical cases were found matching the specified query, status, and date criteria."

    clean_cases = sanitize_payload_data(cases)

    try:
        base_summary = generate_pass1_summary(
            query=query,
            cases=clean_cases,
            user_key=user_key,
            model_api=model_api,
            model_id=MODEL_ID,
        )

        action_hint = '\n\n---\n💡 **Tip**: Type **"summarize all above cases"** to view a root cause analysis and technical synthesis.'
        if "summarize all above cases" not in base_summary.lower():
            base_summary += action_hint

        return base_summary
    except Exception as e:
        sys.stderr.write(f"[Investigation] Failed to generate summary: {e}\n")
        return "Historical cases were retrieved, but the AI summary could not be generated."


def run_investigation(
    query: str,
    user_key: str,
    model_api: str,
    product: Optional[str] = None,
    rows: int = 5,
    start: int = 0,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Orchestrates historical search retrieval and Python-side filtering."""

    # Handle conversation follow-ups
    if history and is_followup_summarization(query):
        sys.stderr.write("[Investigation] Follow-up summarization detected. Resolving from conversation history...\n")

        previous_context = ""
        for msg in reversed(history[:-1]):
            if msg.get("role") == "assistant" and ("Case " in msg.get("content", "") or "04" in msg.get("content", "")):
                previous_context = msg.get("content", "")
                break

        if previous_context:
            system_prompt = (
                "You are a Senior Red Hat Support Architect.\n"
                "The user requested a technical synthesis of the historical support cases previously retrieved in this conversation.\n\n"
                "Instructions:\n"
                "1. Analyze all cases provided in the prior context.\n"
                "2. Identify core problem patterns, shared technical symptoms, and root causes.\n"
                "3. Provide proven resolutions, workarounds, and actionable recommendations.\n\n"
                "Output Structure:\n"
                "## Historical Cases Technical Synthesis\n"
                "- **Common Problem Patterns**:\n"
                "- **Root Cause Analysis**:\n"
                "- **Proven Resolutions & Workarounds**:\n"
                "- **Recommended Next Steps**:"
            )

            prompt = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Prior Retrieved Cases Context:\n{previous_context}\n\nUser Request: {query}"},
            ]
            synthesis_res = ask_llm(prompt, user_key, model_api)["choices"][0]["message"]["content"]
            return {"summary": synthesis_res, "cases": []}

    # Extract clean search query
    search_query = clean_query_for_search(query)

    if not search_query or search_query == "*:*":
        detected_product = product or extract_product(query)
        if detected_product and detected_product in PRODUCT_CATALOG:
            keywords = PRODUCT_CATALOG[detected_product].get("keywords", [])
            if keywords:
                search_query = keywords[0]

    date_filter = extract_date_filter(query)

    sys.stderr.write(
        f"[Investigation] Raw Query: '{query}' -> Solr Term: '{search_query}' | Python Date Filter: {date_filter}\n"
    )

    # Fetch 50 cases from Solr so Python filtering has a large pool to work with
    tool_payload = {
        "query": search_query,
        "rows": 50,
        "start": start,
    }

    try:
        response = execute_tool("search_historical_cases", tool_payload)

        if not response:
            return {"error": "Empty response from Salesforce search."}

        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return {"error": "Failed to parse JSON response from Salesforce search tool."}

        if "error" in response:
            return response

        raw_cases = response.get("cases", response.get("docs", []))
        sys.stderr.write(f"[Investigation] Retrieved {len(raw_cases)} raw cases from Solr.\n")

        # Apply Python Date + Status Filtering
        filtered_cases = filter_cases_by_status_and_date(raw_cases, query, date_filter)
        sys.stderr.write(f"[Investigation] {len(filtered_cases)} cases matched Python Status/Date criteria.\n")

        # Limit to target requested rows (e.g. top 5)
        final_cases = filtered_cases[:rows]

        summary = _generate_investigation_summary(
            query,
            final_cases,
            user_key,
            model_api,
        )

        return {"summary": summary, "cases": final_cases}

    except Exception as e:
        sys.stderr.write(f"[Investigation] Failed: {str(e)}\n")
        return {"error": str(e)}
