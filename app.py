import os
from flask import Flask, request, jsonify, render_template, session
from flask_session import Session
from agent import run_agent

app = Flask(__name__)

# SECURITY REQUIREMENT: Flask sessions require a secret key
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-dev-key-change-this")

# Configure Server-Side Session Storage BEFORE initializing
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False

# Initialize Flask-Session with capital 'S'
Session(app)

# Environment Variables
USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")


# -----------------------------
# GUARDRAIL: INGRESS VERIFICATION
# -----------------------------
def validate_gateway_request(text: str) -> bool:
    """
    Validates general text size bounds at the edge gateway to prevent DoS attempts.
    """
    if not text or len(text.strip()) > 3000:
        return False
    return True


@app.route("/")
def home():
    return render_template("chat.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json or {}
    user_msg = data.get("message", "").strip()

    # GUARDRAIL: Ingress Edge Filtering
    if not user_msg:
        return jsonify({"reply": "No message received."}), 400

    if not validate_gateway_request(user_msg):
        return (
            jsonify(
                {
                    "reply": "Security Error: Input exceeds maximum acceptable length constraints."
                }
            ),
            400,
        )

    # GUARDRAIL & RESTORED FUNCTIONALITY:
    # Read the isolated history for THIS specific user session. Initialize if empty.
    if "history" not in session:
        session["history"] = []

    session_history = session["history"]
    session_history.append({"role": "user", "content": user_msg})

    try:
        # Run the agent with the user's continuous chat history matrix
        answer = run_agent(session_history, USER_KEY, MODEL_API, TOKEN)
    except Exception as e:
        answer = f"Agent Error: {str(e)}"

    # Append assistant reply to this specific user's session state
    session_history.append({"role": "assistant", "content": answer})

    # To keep token sizes under control over long chats, keep only the last 15 messages
    session["history"] = session_history[-15:]

    return jsonify({"reply": answer})


@app.route("/reset", methods=["GET", "POST"])
def reset():
    """Clears the chat history only for the user making the request."""
    session.pop("history", None)
    return jsonify({"status": "Your session context has been cleared."})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
