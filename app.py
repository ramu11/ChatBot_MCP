import os
from flask import Flask, request, jsonify, render_template
from agent import run_agent

app = Flask(__name__)

# Environment Variables
USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")

# Global message history for the session
messages = []

# IMPROVISED Tool definitions: Refined to match your "No Closed Cases" & "Jira Focus" rules
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_support_case",
            "description": (
                "DEEP SCAN: Use this for specific 8-digit Case IDs. "
                "Retrieves case details PLUS technical comments and Jira tracker updates "
                "to provide Status, Target Release, and Progress summaries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "pattern": "^\\d{8}$"}
                },
                "required": ["case_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_cases",
            "description": (
                "FILTER SEARCH: Finds active cases (Waiting on Red Hat/Customer/Engineering). "
                "Results are automatically sorted with the LATEST modified cases at the top."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Search term or SBR name."},
                    "sbrs": {
                        "type": "array",
                        "items": {
                            "type": "string", 
                            "enum": [
                                "Ansible", "API Mgmt", "Business Rule Frameworks", "FuseSource", 
                                "Identity Management", "JBoss Base AS", "JBoss Clustering", 
                                "JBoss Security", "JVM & Diagnostics", "Messaging", "Networking", 
                                "RHOAI", "Security Vulnerabilities", "Services", "Shift", "Webservers"
                            ]
                        }
                    },
                    "maxResults": {"type": "integer", "default": 20}
                },
                "required": ["keyword"]
            }
        }
    }
]

@app.route("/")
def home():
    return render_template("chat.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_msg = data.get("message")
    
    if not user_msg:
        return jsonify({"reply": "No message received."}), 400

    # 1. Update session history
    messages.append({"role": "user", "content": user_msg})

    # 2. Call Agent (Internal logic handles tool selection and deep scanning)
    try:
        answer = run_agent(messages, USER_KEY, MODEL_API, TOKEN)
    except Exception as e:
        answer = f"Agent Error: {str(e)}"

    # 3. Store response
    messages.append({"role": "assistant", "content": answer})

    return jsonify({"reply": answer})

@app.route("/reset", methods=["POST"])
def reset():
    """Utility to clear chat history without restarting server."""
    global messages
    messages = []
    return jsonify({"status": "History cleared"})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
