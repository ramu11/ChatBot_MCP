# llm.py
"""
Low-Level LLM Client Interface for Red Hat AI Support Assistant.

This module manages direct HTTP interaction with OpenAI-compatible API endpoints.
It includes critical prompt-injection guardrails (user string sandboxing), token safety
truncation, structured request logging, and graceful network fail-over handling.
"""

import json
import os
import re
import uuid
from typing import Any, Dict, List

import requests
import urllib3

# Suppress unverified HTTPS warnings for corporate gateway compatibility
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Target model identifier from environment configuration
MODEL_ID = os.getenv("MODEL_ID")


# -------------------------------------------------------------
# SANITIZATION UTILITY
# -------------------------------------------------------------
def clean_case_text(text: str) -> str:
    """
    Strips raw container SHAs, image digests, and repetitive build logs from case text
    before sending context to the LLM.
    """
    if not text:
        return ""

    # Remove image digests (e.g., sha256:c9eba0d1f9fba5887...)
    text = re.sub(r"sha256:[a-f0-9]{32,64}", "[digest]", text)

    # Shorten long registry URLs
    text = re.sub(r"registry\.redhat\.io\/[^\s]+", "[container-image]", text)

    # Collapse repetitive whitespace/newlines
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_linked_resource(res: Any) -> List[str]:
    """
    Normalizes raw backend API URLs (hydra/rest/drupal/solutions/123456)
    to clean, public Red Hat Knowledgebase URLs (https://access.redhat.com/solutions/123456).
    """
    if not res:
        return []

    if isinstance(res, str):
        urls = [u.strip() for u in res.split(",") if u.strip()]
    elif isinstance(res, list):
        urls = [str(u).strip() for u in res if u]
    else:
        urls = []

    normalized_urls = []
    for url in urls:
        # Extract solution ID from hydra/rest/drupal/solutions/<ID> or standard solution paths
        sol_match = re.search(r"solutions/(\d+)", url)
        if sol_match:
            solution_id = sol_match.group(1)
            normalized_urls.append(f"https://access.redhat.com/solutions/{solution_id}")
        else:
            normalized_urls.append(url)

    return normalized_urls


# -------------------------------------------------------------
# PASS 1 SYSTEM PROMPT & LIST GENERATOR
# -------------------------------------------------------------

PASS_1_SYSTEM_PROMPT = """You are a Red Hat support case data formatter. Your task is to output ALL retrieved historical support cases directly using the exact metadata fields provided.

### STRICT OUTPUT FORMAT:
For EACH case retrieved, output ONLY the following format:

**Case Number:** <Case Number>
* **Status:** <Status>
* **Summary:** <Summary>
* **Created By:** <Created By>
* **Linked Resources:** <Comma-separated URLs or 'None'>

---

### STRICT RULES:
1. Do NOT write an "Executive Summary", "Technical Analysis", "Core Patterns", or "Root Causes" section.
2. Do NOT aggregate or synthesize the cases together.
3. List EVERY case individually in the exact format shown above without truncating any cases.
4. Keep the output clean, objective, and accurate to the provided metadata.
"""


def generate_pass1_summary(
    query: str,
    cases: List[Dict[str, Any]],
    user_key: str,
    model_api: str,
    model_id: str = MODEL_ID,
) -> str:
    """
    Formats retrieved historical case metadata using Red Hat API schema keys
    (case_number, case_summary, case_internal_status, case_createdByName, case_linked_resource),
    applies text sanitization, normalizes Knowledgebase URLs, and calls the LLM to output the exact cases.
    """
    formatted_cases = ""
    for idx, c in enumerate(cases, 1):
        # Extract fields prioritizing Red Hat v2 search API schema key names
        case_num = c.get("case_number") or c.get("case") or c.get("CaseNumber") or "N/A"
        status = (
            c.get("case_internal_status") or c.get("status") or c.get("Status") or "N/A"
        )
        summary = clean_case_text(
            c.get("case_summary") or c.get("summary") or c.get("Subject") or "N/A"
        )
        created_by = (
            c.get("case_createdByName")
            or c.get("createdBy")
            or c.get("CreatedBy")
            or "N/A"
        )
        raw_linked = (
            c.get("case_linked_resource")
            or c.get("linkedResources")
            or c.get("linked_resources")
            or []
        )
        linked_res = normalize_linked_resource(raw_linked)

        formatted_cases += f"""
---
Case {idx}:
- Case Number: {case_num}
- Status: {status}
- Summary: {summary}
- Created By: {created_by}
- Linked Resources: {', '.join(linked_res) if linked_res else 'None'}
"""

    user_message = f"""User Query: "{query}"

Retrieved Cases to Format:
{formatted_cases}

Format and list all retrieved cases according to your instructions."""

    messages = [
        {"role": "system", "content": PASS_1_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Execute call using strict zero temperature for deterministic output
    response = ask_llm(
        messages=messages,
        user_key=user_key,
        model_api=model_api,
        model_id=model_id,
        label="PASS_1_CASE_LISTING",
        temperature=0.0,
        max_tokens=2500,
    )

    # Extract assistant content from OpenAI response structure
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return "**Error:** Unable to format case list from LLM response."


# -------------------------------------------------------------
# GUARDRAIL: PROMPT INJECTION & TOKEN BOUNDARY ISOLATION
# -------------------------------------------------------------
def encapsulate_user_prompt(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Enforces rigid execution context isolation boundaries around unstructured user input.
    """
    protected_messages = []

    for m in messages:
        content = m.get("content", "")

        # Truncate payloads exceeding 40,000 characters to ensure token safety
        if len(content) > 40000:
            content = content[:40000] + "\n...[TRUNCATED]..."

        # Encase raw user input in sandbox markers to prevent system instruction overrides
        if m.get("role") == "user":
            content = (
                f"[BEGIN USER SANDBOX CONTEXT]\n{content}\n[END USER SANDBOX CONTEXT]"
            )

        protected_messages.append({"role": m["role"], "content": content})

    return protected_messages


# -------------------------------------------------------------
# MAIN LLM CALL INTERFACE
# -------------------------------------------------------------
def ask_llm(
    messages: List[Dict[str, str]],
    user_key: str,
    model_api: str,
    model_id: str = MODEL_ID,
    label: str = "GENERIC",
    temperature: float = 0.7,
    max_tokens: int = 2500,
) -> Dict[str, Any]:
    """
    Executes an HTTP POST request to the OpenAI-compatible chat completions API.
    """
    base_url = model_api.rstrip("/")
    if base_url.endswith("/v1beta/openai/chat/completions") or base_url.endswith(
        "/chat/completions"
    ):
        url = base_url
    elif base_url.endswith("/v1beta/openai") or base_url.endswith("/v1"):
        url = f"{base_url}/chat/completions"
    else:
        url = f"{base_url}/v1beta/openai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_key}",
    }

    request_id = str(uuid.uuid4())[:8]
    protected_messages = encapsulate_user_prompt(messages)

    payload = {
        "model": model_id,
        "messages": protected_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    print(f"\n[LLM from llm.py][{label}][{request_id}] Calling model={model_id}")

    try:
        response = requests.post(
            url, headers=headers, json=payload, verify=False, timeout=60
        )

        # Parse error payload if response code is not 200 OK
        if not response.ok:
            try:
                err_data = response.json()
                if "error" in err_data and isinstance(err_data["error"], dict):
                    error_detail = err_data["error"].get("message", response.text)
                else:
                    error_detail = response.text
            except Exception:
                error_detail = response.text

            print(
                f"[LLM ERROR] [{label}][{request_id}] Status {response.status_code}: {error_detail}"
            )
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                f"**Technical Alert:** LLM request failed (Status {response.status_code}). Error: {error_detail}"
                            ),
                        }
                    }
                ]
            }

        data = response.json()
        print(
            f"[LLM] [{label}][{request_id}] Call successful (Status: {response.status_code})"
        )

        return data

    except requests.exceptions.RequestException as e:
        # Check specifically for DNS / Name Resolution / Network Connection failures
        if isinstance(e, requests.exceptions.ConnectionError):
            clean_err_msg = "Unable to reach the LLM gateway. Please check network connectivity or host configuration."
        else:
            clean_err_msg = str(e).split(" for url")[0]

        print(f"[LLM ERROR] [{label}][{request_id}]: {clean_err_msg} (Raw: {e})")

        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "**Technical Alert:** LLM request failed. Error: "
                            f"{clean_err_msg}"
                        ),
                    }
                }
            ]
        }
