# llm.py — Handles Gemini LLM calls via OpenAI-compatible endpoint

import requests
import urllib3
import json

# Suppress insecure request warnings for local/private environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ask_llm(messages, user_key, model_api, model_id="gemini-2.0-flash"):
    """
    Sends messages to the Gemini LLM.
    The agent.py logic handles tool execution and injects results
    into the messages list before calling this function.
    """

    # Ensure we use the correct completions endpoint
    url = f"{model_api}/v1beta/openai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_key}"
    }

    # Temperature set to 0.0 for consistent, factual support answers
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 2000  # Allows for detailed case summaries and Jira link formatting
    }

    # DEBUG - Helpful for verifying the injected MCP tool results
    print(f"\n[LLM] Sending Request to Gemini ({model_id})...")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=60 # Matches the robust processing needed for deep Jira scans
        )

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"[LLM] Error: {str(e)}")
        # Return a structured error response that agent.py can parse safely
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"I'm sorry, I'm having trouble connecting to the brain (LLM). Error: {str(e).split(' for url')[0]}"
                    }
                }
            ]
        }
