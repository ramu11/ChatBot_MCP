# ChatBot_MCP

# Red Hat Support Assistant (MCP Edition)

An intelligent support agent that leverages the Model Context Protocol (MCP) to fetch and filter Red Hat support cases, identify related Jira issues, and provide general support guidance using Gemini.

## 🚀 Features

*   **Logic 1: General Search** – Natural language assistance for general Red Hat queries.
*   **Logic 2: Case ID Search** – Instantly fetches details for any 8-digit Red Hat Support case.
*   **Logic 3: Case Filtering** – Search and monitor cases by keyword, status, and SBR (e.g., RHOAI, Messaging, Fuse).
*   **Jira Integration** – Automatically detects and links Jira IDs (e.g., RHOAIRFE, ENTMQST) within tool results.

## 🛠️ Setup & Installation

1.  **Clone the Repository:**

    ```bash
    git clone https://github.com
    cd ChatBot_MCP
    ```
2.  **Install Dependencies:**

    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment Variables:**

    Create a `.env` file and add credentials:

    ```env
    GEMINI_API_KEY=your_key_here
    MCP_SERVER_URL=your_mcp_server_endpoint
    ```
4.  **Run the Application:**

    ```bash
    python app.py
    ```

## 📖 Usage Examples

*   **Fetch a specific case:** "What is the status of case xxxxxxxx?"
*   **Filter for specific issues:** "Search for OOM errors in Messaging" or "Find RHOAI cases waiting on Red Hat"
*   **General help:** "How do I configure JBoss EAP logging?"

## 📂 Project Structure

*   `agent.py`: The core orchestrator managing LLM prompts and MCP tool routing.
*   `llm.py`: Interface for communicating with Gemini.
*   `tools/`: Directory containing `tool_router.py` for executing MCP functions.
*   `mcp_servers/`: Configuration for integrated MCP tool servers.

