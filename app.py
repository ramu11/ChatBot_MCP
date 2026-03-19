import os
from flask import Flask, request, jsonify, render_template
from agent import run_agent

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("chat.html")

# Environment Variables
USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")

# Global message history for the session
messages = []

# Tool definitions mapped to MCP capabilities
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_support_case",
            "description": "Fetch details for a specific 8-digit Red Hat support case ID.",
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
            "description": "Search Red Hat cases by keyword, status, and SBR group.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "statuses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["Waiting on Red Hat"]
                    },
                    "sbrs": {
                        "type": "array",
                        "items": {
                            "type": "string", 
                            "enum": ["FuseSource", "Messaging", "JBoss Security", "RHOAI", "RHEL AI"]
                        }
                    }
                },
                "required": ["keyword"]
            }
        }
    }
]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_msg = data.get("message")
    
    if not user_msg:
        return jsonify({"reply": "No message received."}), 400

    # Add user message to history
    messages.append({
        "role": "user",
        "content": user_msg
    })

    # Call the updated agent logic
    # Note: messages is passed as a list
    answer = run_agent(messages, USER_KEY, MODEL_API, TOKEN)

    # Store assistant's response to maintain conversation history
    messages.append({
        "role": "assistant",
        "content": answer
    })

    return jsonify({"reply": answer})

if __name__ == "__main__":
    # Standard Flask port
    app.run(port=5000, debug=True)

