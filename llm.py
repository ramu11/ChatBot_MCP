import requests
import urllib3
import json
import uuid
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
MODEL_ID = os.getenv("MODEL_ID")


def encapsulate_user_prompt(messages):
    """
    Enforces rigid execution context isolation boundaries around unstructured user strings,
    preventing user instructions from escaping or spoofing system role permissions.
    """
    protected_messages = []
    for m in messages:
        content = m.get("content", "")

        if len(content) > 40000:
            content = content[:40000] + "\n...[TRUNCATED]..."

        # Encase user expressions in strict descriptive tokens
        if m.get("role") == "user":
            content = (
                f"[BEGIN USER SANDBOX CONTEXT]\n{content}\n[END USER SANDBOX CONTEXT]"
            )

        protected_messages.append({"role": m["role"], "content": content})
    return protected_messages


def ask_llm(
    messages,
    user_key,
    model_api,
    model_id=MODEL_ID,
    label="GENERIC",
    temperature=0.7,
    max_tokens=2500,
):
    url = f"{model_api}/v1beta/openai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_key}",
    }

    request_id = str(uuid.uuid4())[:8]

    # Run the structural protection guardrail
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

        response.raise_for_status()

        data = response.json()

        print(
            f"[LLM] [{label}][{request_id}] Call successful (Status: {response.status_code})"
        )

        return data

    except requests.exceptions.RequestException as e:
        error_msg = str(e).split(" for url")[0]
        print(f"[LLM ERROR] [{label}][{request_id}]: {error_msg}")

        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"**Technical Alert:** LLM request failed. Error: {error_msg}",
                    }
                }
            ]
        }
