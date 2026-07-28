
```markdown
# 🤖 ChatBot_MCP

A modular, intent-aware AI Chatbot built with Python and Flask, utilizing the **Model Context Protocol (MCP)** to interact with external tools (Salesforce and Jira) and an evidence-based investigation engine.

---

## 📌 Architecture Overview


```

```
             +-----------------------------------+
             |           User Interface          |
             +-----------------------------------+
                               |
                               v
             +-----------------------------------+
             |          Flask App Layer          |
             |              (app.py)             |
             +-----------------------------------+
                               |
                               v
             +-----------------------------------+
             |          Agent Manager            |
             |             (agent.py)            |
             +-----------------------------------+
                               |
        +----------------------+----------------------+
        |                                             |
        v                                             v

```

+-----------------------+                     +-----------------------+
|  AI Pipeline Module   |                     |     LLM Interface     |
| (ai_pipeline/)        |                     |       (llm.py)        |
| - request_classifier  |                     +-----------------------+
| - investigation_engine|                                 |
| - docs_handler        |                                 v
| - keywords            |                     +-----------------------+
+-----------------------+                     |      Tool Router      |
| (tools/tool_router.py)|
+-----------------------+
|
v
+-----------------------+
|       MCP Client      |
| (tools/mcp_client.py) |
+-----------------------+
|
v
+-----------------------+
|     Salesforce /      |
|     Jira Servers      |
+-----------------------+

```

---

## 🛠️ Component Breakdown

| Module | File | Description |
| :--- | :--- | :--- |
| **App Layer** | `app.py` | Flask web application handling chat routes and user sessions. |
| **Agent Layer** | `agent.py` | Main orchestrator managing classification, data sanitization, Jira table formatting, and flow execution[cite: 1]. |
| **AI Pipeline** | `ai_pipeline/request_classifier.py` | Classifies requests into `case_lookup`, `jira_lookup`, `investigation`, or `general` modes[cite: 3]. |
| | `ai_pipeline/keywords.py` | Defines product catalogs, failure keywords, and query cleaning logic[cite: 2, 3]. |
| | `ai_pipeline/investigation_engine.py` | Searches historical cases via MCP tools and builds structured diagnostic summaries[cite: 2]. |
| | `ai_pipeline/docs_handler.py` | Fetches local documentation context for RAG enrichment[cite: 1]. |
| **LLM Interface**| `llm.py` | Communicates with the LLM API endpoints. |
| **Tools & MCP** | `tools/tool_router.py` | Routes tool calls to MCP clients or direct integrations[cite: 1, 2]. |
| | `tools/mcp_client.py` | MCP protocol handler for remote tool interactions. |

---

## 🔄 Core Request Flows

The chatbot routes requests into one of **four distinct execution paths** based on deterministic matching and LLM intent classification[cite: 1, 3]:

### 1. Investigation Flow (`investigation`)
* **Trigger:** Prompt contains investigation phrases or failure keywords[cite: 3] (or LLM fallback identifies an incident/troubleshooting intent)[cite: 3].
* **Execution:** `agent.py` routes directly to `investigation_engine.py`[cite: 1]. The engine cleans the query, executes the `search_historical_cases` MCP tool, and generates an evidence-based investigation report (Executive Summary, Patterns, Root Causes, Recommendations)[cite: 2].
* **RAG Status:** No RAG[cite: 2]. Direct historical case search + LLM synthesis[cite: 2].

### 2. Salesforce Case Lookup (`case_lookup`)
* **Trigger:** An 8-digit Salesforce case number (e.g., `12345678`) is present in the prompt[cite: 3].
* **Execution:** `agent.py` fetches live case details and comments via MCP tools (`get_support_case`, `list_case_comments`)[cite: 1]. It extracts cross-referenced Jira IDs[cite: 1], enriches them with Jira API calls[cite: 1], redacts sensitive details via `sanitize_payload_data`[cite: 1], and formats a full summary along with a Markdown Jira table[cite: 1].
* **RAG Status:** No RAG[cite: 1]. Direct Salesforce + Jira tool integration[cite: 1].

### 3. Jira Issue Lookup (`jira_lookup`)
* **Trigger:** A Jira issue key (e.g., `PROJECT-1234`) is present in the prompt[cite: 3].
* **Execution:** `agent.py` retrieves issue fields and recent comments via `jira.get_issue` and `jira.get_comments` tools[cite: 1]. The response is sanitized, summarized by the LLM, and presented with a formatted Jira details table[cite: 1].
* **RAG Status:** No RAG[cite: 1]. Direct Jira API execution[cite: 1].

### 4. General / RAG Flow (`general`)
* **Trigger:** General technical questions, pre-upgrade guides, syntax help, or standard product queries[cite: 3].
* **Execution:** 
  * **Product Detected:** If `detect_product` matches a product, `agent.py` invokes `docs_handler.py`[cite: 1, 3]. If relevant context is found, it uses the `RAG_DOCS` prompt mode to synthesize an enriched response[cite: 1].
  * **No Product / No Docs Found:** If no docs context is retrieved, it falls back to direct LLM general knowledge under the `CORE_KB` mode[cite: 1].
* **RAG Status:** **Conditional RAG** (Only invoked when general mode detects a product and matching documentation)[cite: 1, 3].

---

## 🚀 Getting Started

### Prerequisites

* Python 3.10+
* Environment variables configured for model APIs and credentials

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/ramu11/ChatBot_MCP.git](https://github.com/ramu11/ChatBot_MCP.git)
   cd ChatBot_MCP

```

2. **Set up a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

```


3. **Install dependencies:**
```bash
pip install -r requirements.txt

```


4. **Environment Setup:**
Create a `.env` file in the root directory:
```env
MODEL_ID=your_model_id
MODEL_API=your_llm_api_endpoint
USER_KEY=your_llm_key
TOKEN=your_auth_token

```


5. **Run the Application:**
```bash
python app.py

```



```

```