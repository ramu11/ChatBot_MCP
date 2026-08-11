# investigation_engine.py
"""
Investigation Engine Module for Red Hat Support AI Assistant.

This module executes deep incident investigation workflows across historical support cases.
It normalizes user query terms, interfaces with the Salesforce case search tool,
and leverages the LLM to synthesize evidence-based, structured investigation reports.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Union

from ai_pipeline.docs_handler import handle_docs_query
from ai_pipeline.keywords import clean_query_for_search
from llm import ask_llm, generate_pass1_summary
from tools.tool_router import execute_tool

# Environment configuration
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
    """Detects if the user submitted a follow-up summarization request for previously retrieved cases."""
    q = query.lower().strip()
    keywords = [
        "summarize",
        "summary",
        "above cases",
        "these cases",
        "results",
        "findings",
    ]
    return any(k in q for k in keywords) and ("search" not in q and "list" not in q)


# -------------------------------------------------------------
# PRIVATE HELPER: LLM SUMMARY GENERATOR
# -------------------------------------------------------------
def _generate_investigation_summary(
    query: str,
    cases: List[Dict[str, Any]],
    user_key: str,
    model_api: str,
) -> str:
    """
    Delegates Pass 1 formatting to llm.generate_pass1_summary to output a clean,
    individual case list without executive summaries, appending a plain-text prompt hint at the end.
    """
    # Quick exit if search returned zero historical cases
    if not cases:
        return "No historical cases were found matching the query."

    # Sanitize case payload data prior to LLM submission
    clean_cases = sanitize_payload_data(cases)

    try:
        # Delegate directly to llm.py Pass 1 list generator
        base_summary = generate_pass1_summary(
            query=query,
            cases=clean_cases,
            user_key=user_key,
            model_api=model_api,
            model_id=MODEL_ID,
        )

        # Standard plain-text hint appended at the bottom
        action_hint = '\n\n---\n💡 **Tip**: Type **"summarize all above cases"** to view a root cause analysis and technical synthesis.'
        if "summarize all above cases" not in base_summary.lower():
            base_summary += action_hint

        return base_summary
    except Exception as e:
        sys.stderr.write(f"[Investigation] Failed to generate summary: {e}\n")
        return "Historical cases were retrieved, but the AI summary could not be generated."


# -------------------------------------------------------------
# MAIN INVESTIGATION WORKFLOW
# -------------------------------------------------------------
def run_investigation(
    query: str,
    user_key: str,
    model_api: str,
    product: Optional[str] = None,
    rows: int = 5,
    start: int = 0,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Main orchestrator for Pass 1 of the Incident Investigation workflow.

    Pipeline Steps:
        1. Intercept follow-up requests to summarize cases previously fetched from session history.
        2. Clean and optimize raw query text for search tool keyword matching.
        3. Query top historical Salesforce cases (Pass 1 - Metadata search without comment overhead).
        4. Send case metadata findings to LLM engine to format a clean 5-case list with standard text guidance.
        5. Package summary and case objects into result dictionary for caller.
    """
    # -----------------------------------------------------------------
    # STEP 1: FOLLOW-UP INTERCEPTION (Session Context Summarization)
    # -----------------------------------------------------------------
    if history and is_followup_summarization(query):
        sys.stderr.write(
            "[Investigation] Follow-up summarization detected. Resolving from conversation history...\n"
        )

        # Retrieve prior assistant context containing the fetched case list
        previous_context = ""
        for msg in reversed(history[:-1]):
            if msg.get("role") == "assistant" and (
                "Case " in msg.get("content", "") or "04" in msg.get("content", "")
            ):
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
                {
                    "role": "user",
                    "content": f"Prior Retrieved Cases Context:\n{previous_context}\n\nUser Request: {query}",
                },
            ]
            synthesis_res = ask_llm(prompt, user_key, model_api)["choices"][0][
                "message"
            ]["content"]
            return {"summary": synthesis_res, "cases": []}

    # -----------------------------------------------------------------
    # STEP 2: NEW INVESTIGATION SEARCH
    # -----------------------------------------------------------------
    search_query = clean_query_for_search(query)

    sys.stderr.write(
        f"[Investigation] Raw Query: '{query}' -> Search Query: '{search_query}'\n"
    )

    try:
        response = execute_tool(
            "search_historical_cases",
            {"query": search_query, "rows": rows, "start": start},
        )

        if not response:
            return {"error": "Empty response from Salesforce search."}

        # Safe parsing of response if serialized string is returned
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return {
                    "error": "Failed to parse JSON response from Salesforce search tool."
                }

        if "error" in response:
            return response

        cases = response.get("cases", response.get("docs", []))
        sys.stderr.write(f"[Investigation] Retrieved {len(cases)} historical cases.\n")

        # Step 3: Generate clean case list via LLM with plain-text guidance
        summary = _generate_investigation_summary(
            query,
            cases,
            user_key,
            model_api,
        )

        # Step 4: Return packaged summary and raw retrieved case data
        return {"summary": summary, "cases": cases}

    except Exception as e:
        sys.stderr.write(f"[Investigation] Failed: {str(e)}\n")
        return {"error": str(e)}
