I have updated the **README.md** to remove the specific product codes. The descriptions now focus on the **Universal Regex** capability, which allows the agent to identify *any* Red Hat Jira project automatically without needing a predefined list.

---

# ChatBot_MCP

# Red Hat Support Assistant (MCP Edition)

An intelligent support agent that leverages the Model Context Protocol (MCP) to fetch and filter Red Hat support cases, identify related Jira issues, and provide technical summaries using Gemini.

## 🚀 Features

* **Logic 1: Deep Case Analysis** – Automatically triggers a "Triple-Scan" (Case Details + Comments + External Trackers) when an 8-digit ID is detected.
* **Logic 2: Universal Jira Detection** – Employs dynamic Regex to identify and link Jira IDs from technical notes, regardless of the product prefix.
* **Logic 3: Intelligent Filtering** – Monitors active cases ("Waiting" statuses only) with a focus on specific SBRs like **Messaging** or **RHOAI**.
* **Logic 4: Chronological Priority** – Server-side sorting ensures the **Latest/Newest** modified cases are always presented first.



## 📂 Project Structure & File Descriptions

### 🌐 Frontend & Entry
* **`app.py`**: The Flask web server. It manages the chat session history, renders the UI, and defines the `TOOLS` manifest that describes the agent's capabilities to the LLM.

### 🧠 Orchestration (The Brain)
* **`agent.py`**: The core logic engine. It performs pre-processing (Regex detection of Case IDs), orchestrates multi-step tool calls for deep Jira scanning, and enforces strict SBR filtering before calling the LLM.
* **`llm.py`**: The communication bridge to the Gemini API. It handles the 60-second timeout required for deep-data processing and formats the final professional summary.

### 🛠️ Tooling & Infrastructure
* **`salesforce_server.py`**: The FastMCP server. This is the "Engine Room" that communicates directly with the Red Hat API. It enforces sorting (`lastModifiedDate`), handles status filtering, and exposes endpoints for comments and trackers.
* **`tool_router.py`**: The security gatekeeper. It routes authorized tool requests from the agent to the MCP client and ensures the agent has permission to access sensitive technical metadata.



## 🛠️ Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-repo/ChatBot_MCP
    cd ChatBot_MCP
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment Variables:**
    Create a `.env` file:
    ```env
    TOKEN=your_red_hat_api_token
    USER_KEY=your_gemini_api_key
    MODEL_API=your_llm_endpoint_url
    ```
4.  **Run the Application:**
    ```bash
    # Start the MCP Server in one terminal
    python salesforce_server.py
    
    # Start the Web App in another
    python app.py
    ```

## 📖 Usage Examples

* **Case Deep Dive:** "What is the progress on Jira for case 04210225?" (Triggering the Deep Scan).
* **Active Monitoring:** "Filter all Messaging cases" (Enforcing SBR and Waiting statuses).
* **Latest Updates:** "Show me recent RHOAI issues" (Returning newest cases first).

---

