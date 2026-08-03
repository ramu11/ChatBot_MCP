# ai_pipeline/request_classifier.py
"""
Request Classifier Module for Red Hat Support AI Assistant.

This module determines the primary intent and routing workflow for incoming user queries.
It enforces a deterministic routing priority pipeline:

Routing Priority:
    1. Salesforce Case Lookup (8-digit ID check)
    2. Jira Issue Lookup (Project key + number check)
    3. Product Detection (Catalog term matching)
    4. Investigation Keyword Detection (Deterministic term check)
    5. LLM Fallback Routing (General vs. Investigation classification)
"""

import json
import os
import re
from typing import Dict, Any, Optional

from llm import ask_llm
from ai_pipeline.keywords import (
    PRODUCT_CATALOG,
    INVESTIGATION_KEYWORDS,
    FAILURE_KEYWORDS,
)

# ---------------------------------------------------------------------
# ENVIRONMENT CONFIGURATION
# ---------------------------------------------------------------------
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
# HELPER FUNCTIONS
# ---------------------------------------------------------------------


def detect_product(query: str) -> Optional[str]:
    """
    Detects known Red Hat products mentioned in the incoming user query.

    Matching Strategy:
        1. Case-insensitive normalization.
        2. Clean and normalize extra whitespace.
        3. Prioritize matching longer phrases before shorter keywords.
        4. Apply word-boundary checks for single-word keywords to avoid partial matches.
        5. Return the first matching product identifier.

    Args:
        query (str): Raw user query string.

    Returns:
        Optional[str]: Detected product key string from catalog, or None if no match.
    """
    # Normalize query string spacing and lowercase
    q = " ".join(query.lower().split())

    # Iterate through catalog products and match keywords sorted by length (descending)
    for product, metadata in PRODUCT_CATALOG.items():
        keywords = metadata.get("keywords", [])

        # Sort keywords long-to-short so longer exact phrases match first
        for keyword in sorted(keywords, key=len, reverse=True):
            keyword = keyword.lower().strip()

            # Multi-word phrase matching (e.g., "openshift container platform")
            if " " in keyword:
                if keyword in q:
                    return product

            # Whole-word exact keyword matching (e.g., "rhel")
            elif re.search(rf"\b{re.escape(keyword)}\b", q):
                return product

    return None


def is_investigation(query: str, product: Optional[str] = None) -> bool:
    """
    Evaluates if a query represents a troubleshooting or incident analysis request.

    Uses deterministic rule-based keyword matching across explicit investigation
    phrases, failure indicator terms, and combined product-failure rules.

    Args:
        query (str): Raw user query string.
        product (Optional[str]): Detected product key, if any.

    Returns:
        bool: True if investigation or failure indicators exist, False otherwise.
    """
    q = query.lower()

    # Step 1: Check for explicit investigation phrases (e.g., "known issue", "list cases")
    for keyword in INVESTIGATION_KEYWORDS:
        pattern = rf"\b{re.escape(keyword.lower())}\b"
        if re.search(pattern, q):
            return True

    # Step 2: Check for failure / error / crash whole-word indicators
    has_failure_kw = any(
        re.search(rf"\b{re.escape(kw.lower())}\b", q) for kw in FAILURE_KEYWORDS
    )
    if has_failure_kw:
        return True

    # Step 3: Dynamic Rule - If both a Product AND Failure Keyword exist
    if product and has_failure_kw:
        return True

    return False


# ---------------------------------------------------------------------
# MAIN REQUEST CLASSIFIER
# ---------------------------------------------------------------------


def classify_request(query: str, user_key: str, model_api: str) -> Dict[str, Any]:
    """
    Executes the full classification pipeline to determine request routing.

    Pipeline Steps:
        1. Check for 8-digit Salesforce Case numbers.
        2. Check for standard Jira ticket identifiers.
        3. Scan for Red Hat product names.
        4. Detect investigation/failure keywords using `is_investigation`.
        5. Fallback to LLM zero-shot classification if deterministic steps pass.

    Args:
        query (str): The raw text query submitted by the user.
        user_key (str): Authentication key passed to LLM client.
        model_api (str): Target API endpoint URL for LLM call.

    Returns:
        Dict[str, Any]: Dictionary containing classification results:
            - "mode": "case_lookup" | "jira_lookup" | "investigation" | "general"
            - "product": Detected product string or None
            - "confidence": Confidence score float (0.0 to 1.0)
            - "identifier": Case or Jira ID string (if applicable)
    """
    query = query.strip()

    # --------------------------------------------------------------
    # Priority 1: Salesforce Case Lookup (8-digit numerical ID)
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
    # Priority 2: Jira Issue Lookup (Project Key + Number format)
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
    # Priority 3: Product Detection
    # --------------------------------------------------------------
    product = detect_product(query)
    if product:
        print(f"[CLASSIFIER] Product detected: {product}")

    # --------------------------------------------------------------
    # Priority 4: Deterministic Investigation Keyword Detection
    # --------------------------------------------------------------
    if is_investigation(query, product=product):
        print("[CLASSIFIER] Investigation detected using keyword rules.")
        return {
            "mode": "investigation",
            "product": product,
            "confidence": 1.0,
        }

    # --------------------------------------------------------------
    # Priority 5: LLM Fallback Classification
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

        # Defensive payload extraction to prevent KeyError on empty response choices
        choices = response.get("choices", [])
        if not choices:
            raise KeyError("Response choices empty")

        message = choices[0].get("message", {})
        raw_content = message.get("content", "")

        # Check for technical alerts/network error messages returned by llm.py
        if "Technical Alert:" in raw_content or not raw_content:
            print(
                "[CLASSIFIER WARNING] LLM gateway returned alert or empty response. Defaulting to 'general'."
            )
            mode = "GENERAL"
        else:
            mode = raw_content.strip().upper()

        print(f"[CLASSIFIER] LLM Output: {mode}")

        return {
            "mode": "investigation" if "INVESTIGATION" in mode else "general",
            "product": product,
            "confidence": 0.95 if "Technical Alert:" not in raw_content else 0.50,
        }

    except Exception as e:
        # Fallback handling if LLM API call fails or times out
        print(f"[CLASSIFIER ERROR] LLM classification failed ({type(e).__name__}: {e})")
        return {
            "mode": "general",
            "product": product,
            "confidence": 0.50,
        }
