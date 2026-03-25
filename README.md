I have updated the README to include the new Logic 5: Hybrid & General Query Handling and added a dedicated Search & Query Strings section. This ensures users know exactly how to trigger the different "Logics" you've built into agent.py.

ChatBot_MCP
Red Hat Support Assistant (MCP Edition)
An intelligent support agent that leverages the Model Context Protocol (MCP) to fetch and filter Red Hat support cases, identify related Jira issues, and provide technical summaries using Gemini.

🚀 Features
Logic 1: Deep Case Analysis – Automatically triggers a "Triple-Scan" (Case Details + Comments + External Trackers) when an 8-digit ID is detected.

Logic 2: Direct Jira Enrichment – When a Jira ID is provided directly, the agent calls the Jira MCP tool to fetch real-time engineering status and comments.

Logic 3: Intelligent Filtering – Monitors active cases ("Waiting" statuses only) with a focus on specific SBRs like Messaging or RHOAI.

Logic 4: Chronological Priority – Server-side sorting ensures the Latest/Newest modified cases are always presented first.

Logic 5: Hybrid & General Query Handling – Smart routing that handles Case/Jira combinations, "No Jira" scenarios, and general conversational queries without breaking.

📂 Project Structure & File Descriptions
🌐 Frontend & Entry
app.py: The Flask web server. It manages chat sessions and defines the TOOLS manifest.

🧠 Orchestration (The Brain)
agent.py: The core logic engine. Performs Regex detection for Case/Jira IDs and orchestrates the Priority Cascade (Salesforce -> Jira -> LLM).

llm.py: The bridge to the Gemini API. Handles timeouts and formats the final technical summary.

🛠️ Tooling & Infrastructure
salesforce_server.py: The FastMCP server (The Engine Room). Communicates with Red Hat APIs and the Jira Atlassian REST API.

tool_router.py: The security gatekeeper. Routes authorized tool requests from the agent to the MCP client.

🔍 Search & Query Strings
The agent uses specific regex patterns to determine the execution path. Use the following strings to trigger different workflows:

1. Salesforce Case Queries (8-Digit Numeric)
Trigger Logic: get_support_case + list_case_comments + get_external_updates

Query: "Show status for case 04210225"

Query: "What is the latest on 03991244?"

2. Direct Jira Queries (Project-Number Format)
Trigger Logic: Direct call to get_jira_details via Jira MCP tool.

Query: "Check the status of ENTMQBR-10429"

Query: "Give me details on RHOAI-4521"

3. Hybrid Queries (Both Case and Jira)
Trigger Logic: Salesforce Deep Scan + Targeted Jira Enrichment.

Query: "Fetch details for case 04210225 and check if ENTMQBR-10429 is linked."

4. SBR & Status Filters
Trigger Logic: search_cases with predefined SBR filters.

Query: "Search for Messaging cases"

Query: "Show me active RHOAI issues"

5. General Conversation
Trigger Logic: Direct LLM Fallback (No tools called).

Query: "Hello, how can you help me today?"

Query: "What are the supported Red Hat products?"

🛠️ Setup & Installation
Clone the Repository:

Bash
git clone https://github.com/your-repo/ChatBot_MCP
cd ChatBot_MCP
Install Dependencies:

Bash
pip install -r requirements.txt
Configure Environment Variables:
Create a .env file:

Code snippet
TOKEN=your_red_hat_api_token
USER_KEY=your_gemini_api_key
MODEL_API=your_llm_endpoint_url
EMAIL=your_redhat_email
JIRA_TOKEN=your_jira_personal_access_token
Run the Application:

Bash
# Terminal 1: Start the MCP Server
python salesforce_server.py

# Terminal 2: Start the Web App
python app.py
📖 Usage Examples
Case Deep Dive: "What is the progress on Jira for case 04210225?" (Triggering the Deep Scan).

Active Monitoring: "Filter all Messaging cases" (Enforcing SBR and Waiting statuses).

Jira Check: "Summarize the engineering progress for ENTMQBR-10429."
