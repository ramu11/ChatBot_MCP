"""
investigation_engine.py

Implements the Investigation workflow for the AI Support Copilot.

Responsibilities:
- Search historical Salesforce support cases.
- Execute the Salesforce MCP tool.
- Generate an AI investigation summary.
- Return the summary along with retrieved cases.

Future enhancements:
- Case Card extraction
- Pattern detection
- Cross-source correlation (Jira, RAG, KCS)
"""

import json
import os
import sys

from ai_pipeline.keywords import clean_query_for_search
from llm import ask_llm
from tools.tool_router import execute_tool

# Environment Variables
USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")
MODEL_ID = os.getenv("MODEL_ID")


def _generate_investigation_summary(
    query: str,
    cases: list,
    user_key: str,
    model_api: str,
) -> str:
    """
    Generate an evidence-based investigation summary from historical
    Salesforce support cases.

    The summary highlights recurring patterns, common root causes,
    engineering insights, and recommended next steps based solely on the
    retrieved cases.

    Args:
        query:
            Original user investigation request.
        cases:
            Historical Salesforce cases returned by the search.
        user_key:
            LLM API authentication token.
        model_api:
            LLM endpoint URL.

    Returns:
        Investigation summary as plain text. Returns a fallback message if
        summary generation fails.
    """

    if not cases:
        return "No historical cases were found matching the query."

    system_prompt = """
You are a Senior Red Hat Support Engineer.

Analyze historical Red Hat support cases and produce an evidence-based investigation report.

Rules:
- Base your analysis ONLY on the provided historical cases.
- Never invent facts, root causes, versions, or resolutions.
- Clearly distinguish observations from conclusions.
- If the evidence is weak or inconsistent, explicitly state that.
- Quote case numbers when referencing evidence.
- Identify patterns only if supported by multiple cases.
- Be concise, objective, and technically accurate.
- Use professional Red Hat support terminology.
"""

    user_prompt = f"""
User Investigation Request:
{query}

Historical Cases:
{json.dumps(cases, indent=2)}

Generate the following report.

## Executive Summary
- Summarize the investigation in 3-5 bullet points.

## Similar Historical Cases
- List relevant case numbers with a one-line summary.
- Explain why each case is relevant.

## Recurring Patterns
- Identify recurring symptoms, errors, products, or configurations.
- State "No recurring pattern identified" if applicable.

## Root Cause Analysis
- Summarize the most common root causes supported by the evidence.
- If insufficient evidence exists, state that.

## Engineering Insights
- Highlight affected products, versions, configurations, known bugs, or KB articles referenced by the cases.

## Recommended Next Steps
- Recommend practical investigation or troubleshooting steps based only on the historical evidence.

## Confidence
Provide one of:
- High
- Medium
- Low

Briefly explain the confidence level.
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    try:

        response = ask_llm(
            messages,
            user_key,
            model_api,
            model_id=MODEL_ID,
            label="INVESTIGATION_SUMMARY",
            temperature=0,
            max_tokens=2048,
        )

        choices = response.get("choices", [])
        if not choices:
            raise KeyError("Response choices empty")

        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ValueError("LLM returned empty summary content.")

        return content.strip()

    except Exception as e:

        sys.stderr.write(f"[Investigation] Failed to generate summary: {e}\n")

        return (
            "Historical cases were retrieved, but the AI "
            "summary could not be generated."
        )


def run_investigation(
    query: str,
    user_key: str,
    model_api: str,
    product: str = None,
    rows: int = 5,
    start: int = 0,
):
    """
    Execute the Investigation workflow.

    The workflow:
    1. Rewrite and clean the user's query for improved search retrieval.
    2. Search historical Salesforce support cases using MCP tools.
    3. Generate an AI investigation summary from retrieved evidence.
    4. Return both the summary and matching historical cases.

    Args:
        query:
            User investigation request.
        user_key:
            LLM API authentication token.
        model_api:
            LLM endpoint URL.
        product:
            Product identified by the request classifier.
        rows:
            Maximum number of historical cases to retrieve.
        start:
            Starting offset for pagination.

    Returns:
        A dictionary containing the investigation summary and retrieved
        historical cases, or an error message if the investigation fails:
        {
            "summary": "...",
            "cases": [...]
        }
        or
        {
            "error": "..."
        }
    """

    # Clean and normalize query terms for the search tool
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

        if isinstance(response, str):
            response = json.loads(response)

        if "error" in response:
            return response

        cases = response.get("cases", [])

        sys.stderr.write(f"[Investigation] Retrieved {len(cases)} historical cases.\n")

        summary = _generate_investigation_summary(
            query,
            cases,
            user_key,
            model_api,
        )

        return {"summary": summary, "cases": cases}

    except Exception as e:

        sys.stderr.write(f"[Investigation] Failed: {str(e)}\n")

        return {"error": str(e)}
