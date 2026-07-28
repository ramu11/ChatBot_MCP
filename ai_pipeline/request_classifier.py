"""
request_classifier.py

Determines the routing workflow for incoming user requests.

Routing priority:

1. Salesforce Case Lookup
2. Jira Lookup
3. Product Detection
4. Investigation Keyword Detection
5. LLM Intent Routing
"""

import os
import re
import json

from llm import ask_llm
from ai_pipeline.keywords import (
    PRODUCT_CATALOG,
    INVESTIGATION_KEYWORDS,
    FAILURE_KEYWORDS,
)

# Environment Variables
USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")
MODEL_ID = os.getenv("MODEL_ID")


# ---------------------------------------------------------------------
# LLM ROUTER PROMPT
# ---------------------------------------------------------------------

CLASSIFIER_PROMPT = """
You are a routing component inside a Red Hat Support AI Assistant.

Your ONLY responsibility is to classify the user's request into ONE of two categories.

GENERAL
or
INVESTIGATION

GENERAL includes:
- Standard product documentation and official manuals
- Pre-upgrade guidance, installation prerequisites, and best practices
- General how-to questions, feature explanations, and command syntaxes

INVESTIGATION includes:
- Production incidents, failures, crashes, or unexpected restarts (e.g., restarts after an upgrade)
- Troubleshooting unexpected runtime behavior, errors, or post-upgrade issues
- Searching historical Salesforce support cases or known issue databases
- "Have we seen this before?", "Known issue", or case correlation
- JVM/thread/heap dump analysis and postmortem investigation

Return EXACTLY one word.

GENERAL

or

INVESTIGATION

Do not explain.
Do not use markdown.
Do not output anything else.
"""


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------


def detect_product(query: str):
    """
    Detect the Red Hat product mentioned in the user query.

    Matching strategy
    -----------------
    1. Case-insensitive matching.
    2. Normalize whitespace.
    3. Match longer phrases before shorter keywords.
    4. Use whole-word matching for single-word keywords.
    5. Return the first matching product.

    Args:
        query (str):
            User query.

    Returns:
        str | None:
            Product identifier if detected, otherwise None.
    """

    q = " ".join(query.lower().split())

    for product, metadata in PRODUCT_CATALOG.items():

        keywords = metadata.get("keywords", [])

        for keyword in sorted(keywords, key=len, reverse=True):

            keyword = keyword.lower().strip()

            # Multi-word phrase
            if " " in keyword:
                if keyword in q:
                    return product

            # Whole-word keyword
            elif re.search(rf"\b{re.escape(keyword)}\b", q):
                return product

    return None


def is_investigation(query: str) -> bool:
    """
    Determine whether the request is an investigation request using
    deterministic keyword matching across both investigation and failure terms.
    """
    q = query.lower()

    # Check for explicit investigation phrases
    if any(keyword in q for keyword in INVESTIGATION_KEYWORDS):
        return True

    # Check for general failure / troubleshooting indicators
    if any(re.search(rf"\b{re.escape(kw)}\b", q) for kw in FAILURE_KEYWORDS):
        return True

    return False


# ---------------------------------------------------------------------
# REQUEST CLASSIFICATION
# ---------------------------------------------------------------------


def classify_request(query: str, user_key: str, model_api: str) -> dict:
    """
    Classify the incoming request.

    Routing priority

    1. Salesforce Case Number
    2. Jira Issue
    3. Product Detection
    4. Investigation Keyword Detection
    5. LLM Classification (fallback only)

    Returns:

    {
        "mode": "...",
        "product": "...",
        "confidence": 1.0,
        "identifier": "..."
    }
    """

    query = query.strip()

    # --------------------------------------------------------------
    # 1. Salesforce Case
    # --------------------------------------------------------------

    case_match = re.search(r"\b(\d{8})\b", query)

    if case_match:

        print(f"[CLASSIFIER] Salesforce case detected: {case_match.group(1)}")

        return {
            "mode": "case_lookup",
            "product": None,
            "confidence": 1.0,
            "identifier": case_match.group(1),
        }

    # --------------------------------------------------------------
    # 2. Jira Issue
    # --------------------------------------------------------------

    jira_match = re.search(r"\b([A-Z]{2,10}-[0-9]+)\b", query)

    if jira_match:

        print(f"[CLASSIFIER] Jira issue detected: {jira_match.group(1).upper()}")

        return {
            "mode": "jira_lookup",
            "product": None,
            "confidence": 1.0,
            "identifier": jira_match.group(1).upper(),
        }

    # --------------------------------------------------------------
    # 3. Product Detection
    # --------------------------------------------------------------

    product = detect_product(query)

    if product:
        print(f"[CLASSIFIER] Product detected: {product}")

    # --------------------------------------------------------------
    # 4. Investigation Keyword Detection
    # --------------------------------------------------------------

    if is_investigation(query):

        print("[CLASSIFIER] Investigation detected using keyword rules.")

        return {
            "mode": "investigation",
            "product": product,
            "confidence": 1.0,
        }

    # --------------------------------------------------------------
    # 5. LLM Fallback
    # --------------------------------------------------------------

    messages = [
        {
            "role": "system",
            "content": CLASSIFIER_PROMPT,
        },
        {
            "role": "user",
            "content": query,
        },
    ]

    try:

        response = ask_llm(
            messages,
            user_key,
            model_api,
            model_id=MODEL_ID,
            label="REQUEST_CLASSIFIER",
            temperature=0,
            max_tokens=512,
        )

        # Defensive content extraction to prevent KeyError on empty/missing content
        choices = response.get("choices", [])
        if not choices:
            raise KeyError("Response choices empty")

        message = choices[0].get("message", {})
        raw_content = message.get("content")

        if not raw_content:
            print(
                "[CLASSIFIER WARNING] LLM returned empty content. Falling back to default."
            )
            mode = "GENERAL"
        else:
            mode = raw_content.strip().upper()

        print(f"[CLASSIFIER] LLM Output: {mode}")

        return {
            "mode": "investigation" if mode == "INVESTIGATION" else "general",
            "product": product,
            "confidence": 0.95,
        }

    except Exception as e:
        print(f"[CLASSIFIER ERROR] LLM classification failed ({type(e).__name__}: {e})")

        return {
            "mode": "general",
            "product": product,
            "confidence": 0.50,
        }
