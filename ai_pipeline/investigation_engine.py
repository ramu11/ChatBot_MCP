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
    individual case list without executive summaries.
    """
    # Quick exit if search returned zero historical cases
    if not cases:
        return "No historical cases were found matching the query."

    # Sanitize case payload data prior to LLM submission
    clean_cases = sanitize_payload_data(cases)

    try:
        # Delegate directly to llm.py Pass 1 list generator
        return generate_pass1_summary(
            query=query,
            cases=clean_cases,
            user_key=user_key,
            model_api=model_api,
            model_id=MODEL_ID,
        )
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
) -> Dict[str, Any]:
    """
    Main orchestrator for Pass 1 of the Incident Investigation workflow.

    Pipeline Steps:
        1. Clean and optimize raw query text for search tool keyword matching.
        2. Query top historical Salesforce cases (Pass 1 - Metadata search without comment overhead).
        3. Send case metadata findings to LLM engine to format a clean 5-case list.
        4. Package summary and case objects into result dictionary for caller.
    """
    # Step 1: Clean query string (stripping stop words, noise characters)
    search_query = clean_query_for_search(query)

    sys.stderr.write(
        f"[Investigation] Raw Query: '{query}' -> Search Query: '{search_query}'\n"
    )

    try:
        # Step 2: Pass 1 Search - Search cases only using primary metadata
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

        cases = response.get("cases", [])
        sys.stderr.write(f"[Investigation] Retrieved {len(cases)} historical cases.\n")

        # Step 3: Generate clean case list via LLM
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
