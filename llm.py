# llm.py — Handles Gemini LLM calls via OpenAI-compatible endpoint
import requests
import urllib3
import json

# Suppress insecure request warnings for internal Red Hat proxies
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ask_llm(messages, user_key, model_api, model_id="gemini-2.0-flash"):
    """
    Sends processed support data to Gemini Flash.
    Includes truncation to prevent 413 'Request Entity Too Large' errors.
    """
    url = f"{model_api}/v1beta/openai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_key}"
    }

    # Payload protection: Prevents 10MB log dumps from crashing the API call
    protected_messages = []
    for m in messages:
        content = m.get('content', '')
        if len(content) > 40000:
            content = content[:40000] + "\n...[Technical Data Truncated for Size]..."
        
        protected_messages.append({
            "role": m['role'],
            "content": content
        })

    # temperature=0.0 ensures high factual consistency for support summaries
    payload = {
        "model": model_id,
        "messages": protected_messages,
        "temperature": 0.0,
        "max_tokens": 2000 
    }

    print(f"\n[LLM] Summarizing Jira/Case data via {model_id}...")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False, 
            timeout=60    
        )

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"[LLM] Connection Error: {str(e)}")
        # Matches the [0] index access in agent.py
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"**Technical Alert:** I could not reach the LLM gateway. Error: {str(e).split(' for url')[0]}"
                    }
                }
            ]
        }
