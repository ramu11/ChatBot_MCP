# llm.py — Handles Gemini LLM calls via OpenAI-compatible endpoint
import requests
import urllib3
import json

# Suppress insecure request warnings for local/private environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ask_llm(messages, user_key, model_api, model_id="gemini-2.0-flash"):
    """
    Sends messages to the Gemini LLM.
    Includes payload protection to prevent 413 Request Entity Too Large errors.
    """
    # Ensure we use the correct completions endpoint
    url = f"{model_api}/v1beta/openai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_key}"
    }

    # Payload protection: Iterate through messages and truncate massive technical dumps
    # This ensures a single case with 10MB of logs doesn't crash the API call.
    protected_messages = []
    for m in messages:
        content = m.get('content', '')
        # 40,000 characters is a safe limit for most OpenAI-compatible gateways
        if len(content) > 40000:
            content = content[:40000] + "\n...[Technical Data Truncated for Size]..."
        
        protected_messages.append({
            "role": m['role'],
            "content": content
        })

    # Temperature set to 0.0 for consistent, factual support answers
    payload = {
        "model": model_id,
        "messages": protected_messages,
        "temperature": 0.0,
        "max_tokens": 2000 # Enough for detailed summaries and Markdown links
    }

    # DEBUG - Helpful for tracking the request
    print(f"\n[LLM] Sending Request to {model_id}...")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False, # Necessary for some Red Hat internal proxies
            timeout=60    # Matches the robust processing needed for deep Jira scans
        )

        # Check for HTTP errors before parsing JSON
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"[LLM] Error: {str(e)}")
        # Return a structured error response that agent.py can handle gracefully
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"I'm sorry, I'm having trouble connecting to the LLM. Error: {str(e).split(' for url')[0]}"
                    }
                }
            ]
        }
