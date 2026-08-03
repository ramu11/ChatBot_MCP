import os
from flask import Flask, request, jsonify, render_template, session
from flask_session import Session
from agent import run_agent

app = Flask(__name__)

# ------------------------------------------------------------------
# SECURITY & LOCAL DISK SESSION CONFIGURATION
# ------------------------------------------------------------------
# SECURITY REQUIREMENT: Secret key used to sign session cookies
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-dev-key-change-this")

# SERVER-SIDE SESSION CONFIGURATION:
# Store session files on local disk under ./flask_session instead of standard 4KB browser cookies.
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "./flask_session"  # Local disk folder path
app.config["SESSION_PERMANENT"] = True  # Retain session across browser restarts
app.config["PERMANENT_SESSION_LIFETIME"] = (
    86400  # Memory active for 24 hours (in seconds)
)

# Initialize Flask-Session with server-side filesystem backend
Session(app)

# Environment Variables for Model Access
USER_KEY = os.getenv("USER_KEY")
MODEL_API = os.getenv("MODEL_API")
TOKEN = os.getenv("TOKEN")


# ------------------------------------------------------------------
# GUARDRAIL: INGRESS VERIFICATION
# ------------------------------------------------------------------
def validate_gateway_request(text: str) -> bool:
    """
    Validates general text size bounds at the edge gateway to prevent DoS attempts.
    Caps incoming prompts at 3,000 characters.
    """
    if not text or len(text.strip()) > 3000:
        return False
    return True


# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------
@app.route("/")
def home():
    """Renders the main Chatbot Web UI."""
    return render_template("chat.html")


@app.route("/chat", methods=["POST"])
def chat():
    """
    Primary chat API endpoint. Reads session history from local disk,
    appends the new prompt, delegates to the agent orchestrator,
    and persists the updated conversation state back to disk.
    """
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

    # SESSION MEMORY MANAGEMENT:
    # Retrieve user-isolated history matrix from local disk storage. Initialize if empty.
    if "history" not in session:
        session["history"] = []

    session_history = session["history"]
    session_history.append({"role": "user", "content": user_msg})

    try:
        # Run agent orchestrator with continuous message history matrix
        answer = run_agent(session_history, USER_KEY, MODEL_API, TOKEN)
    except Exception as e:
        app.logger.error(f"Agent Execution Error: {str(e)}")
        answer = f"Agent Error: {str(e)}"

    # Append assistant reply to user's local session history
    session_history.append({"role": "assistant", "content": answer})

    # HIGH-CAPACITY HISTORY TRIMMING:
    # Retain the last 30 turns (15 user messages + 15 assistant replies) to allow deep context
    # without exceeding LLM context window limits.
    session["history"] = session_history[-30:]

    return jsonify({"reply": answer})


@app.route("/reset", methods=["GET", "POST"])
def reset():
    """Clears the local disk chat history for the requesting user session."""
    session.pop("history", None)
    return jsonify({"status": "Your session context has been cleared."})


# ------------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Ensure local filesystem session directory exists on local disk before launching app
    os.makedirs("./flask_session", exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)
