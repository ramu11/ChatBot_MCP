# llm.py — Handles Gemini LLM calls via OpenAI-compatible endpoint
# ---------------------------------------------------------------
import requests
import urllib3
import json
import uuid

# Suppress insecure request warnings (common in internal proxy setups)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def ask_llm(
    messages,
    user_key,
    model_api,
    model_id="gemini-2.5-pro",
    label="GENERIC",
    temperature=0.7,            # Added parameter support
    max_tokens=2500             # Added parameter support
):
    """
    Generic LLM caller used across the agent with customizable controls.
    """
    url = f"{model_api}/v1beta/openai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_key}"
    }

    request_id = str(uuid.uuid4())[:8]

    # PAYLOAD PROTECTION
    protected_messages = []
    for m in messages:
        content = m.get("content", "")

        if len(content) > 40000:
            content = content[:40000] + "\n...[TRUNCATED]..."

        protected_messages.append({
            "role": m["role"],
            "content": content
        })

    # Assigned dynamic settings to payload mapping
    payload = {
        "model": model_id,
        "messages": protected_messages,
        "temperature": temperature,   
        "max_tokens": max_tokens      
    }

    print(f"\n[LLM][{label}][{request_id}] Calling model={model_id}")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=60
        )

        response.raise_for_status()
        print(f"[LLM][{label}][{request_id}] Status Code: {response.status_code}")
        data = response.json()
        print(f"[LLM][{label}][{request_id}] Response received successfully")
        return data

    except requests.exceptions.RequestException as e:
        error_msg = str(e).split(" for url")[0]
        print(f"[LLM][{label}][{request_id}] ERROR: {error_msg}")

        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "**Technical Alert:** "
                            f"LLM request failed. Error: {error_msg}"
                        )
                    }
                }
            ]
        }
