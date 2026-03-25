---

# ChatBot_MCP

## Red Hat Support Assistant (MCP Edition)

An intelligent support agent that leverages the **Model Context Protocol (MCP)** to fetch and analyze Red Hat support cases, enrich them with Jira data, and generate concise technical summaries using an LLM.

---

# 🚀 Features

### 🔍 Logic 1: Deep Case Analysis (Triple-Scan)

Automatically triggers a full scan when an 8-digit case ID is detected:

* Case Details
* Case Comments
* External Tracker Updates

This ensures **no Jira reference is missed**.

---

### 🔗 Logic 2: Direct Jira Enrichment

When a Jira ID (e.g., `CSB-7587`) is detected:

* Calls Jira MCP tool (`get_jira_details`)
* Fetches:

  * Status
  * Summary
  * Priority
  * Components / Versions
  * **Jira comments (ADF → plain text)**

---

### 🧠 Logic 3: Intelligent Filtering

Supports filtering of active cases:

* Status:

  * Waiting on Red Hat
  * Waiting on Engineering
  * Waiting on Customer
* SBR filtering (e.g., Messaging, RHOAI)

---

### ⏱️ Logic 4: Chronological Priority

* Server-side sorting by **lastModifiedDate**
* Always shows **latest updates first**

---

### 🔄 Logic 5: Hybrid Query Handling

Handles:

* Case only
* Jira only
* Case + Jira
* No Jira scenarios
* General queries

---

### 📊 Logic 6: Deterministic Rendering (NEW)

* Clean **horizontal tables**
* Consistent structure (no broken markdown)
* Jira IDs rendered as **clickable links**

Example:

```
| Jira | Status | Summary | Priority | Components | Versions |
|------|--------|---------|----------|------------|----------|
| CSB-7587 | In Progress | Add support... | Major | Camel | CSB-4.8.5 |
```

---

### 🔗 Logic 7: Clickable Jira Links (NEW)

* Jira IDs rendered as hyperlinks:

```
[CSB-7587](https://redhat.atlassian.net/browse/CSB-7587)
```

---

### 💬 Logic 8: Engineering Insights (Jira Comment Summary) (NEW)

* Extracts Jira comments from:

  ```
  fields.comment.comments[]
  ```
* Converts ADF → plain text
* Displays **summarized insights**

Example:

```
Engineering Insights:
- Could somebody take a look at this.
- Created external case link for 04379648.
```

---

# 📂 Project Structure

## 🌐 Frontend & Entry

**app.py**

* Flask web server
* Manages chat sessions
* Defines tool manifest

---

## 🧠 Orchestration (Core Logic)

**agent.py**

* Regex detection (Case ID / Jira ID)
* Executes workflow:

  * Case → Triple Scan
  * Jira → Direct fetch
* Builds:

  * Jira tables
  * Engineering insights
* Handles tool responses + formatting

---

**llm.py**

* Connects to LLM (Gemini or compatible)
* Generates executive summaries

---

## 🛠️ Tooling Layer

**salesforce_server.py** (MCP Server)

* Fetches:

  * Case details
  * Case comments
  * External trackers
* Calls Jira REST API:

  ```
  GET /rest/api/3/issue/{jira_id}
  ```
* Extracts:

  * Jira metadata
  * Jira comments (ADF parsing)
* Returns structured JSON:

  ```json
  {
    "key": "CSB-7587",
    "href": "https://redhat.atlassian.net/browse/CSB-7587",
    "status": "...",
    "summary": "...",
    "recent_comments": [...]
  }
  ```

---

**tool_router.py**

* Secure routing layer
* Ensures only authorized tools are invoked

---

# 🔍 Query Patterns

## 1. 📁 Salesforce Case Queries

Trigger: Triple Scan

Examples:

* "Show status for case 04210225"
* "What is the latest on 03991244?"

---

## 2. 🔗 Direct Jira Queries

Trigger: `get_jira_details`

Examples:

* "Check ENTMQBR-10429"
* "Get CEQ-12628 details"

---

## 3. 🔄 Hybrid Queries

Trigger: Case + Jira enrichment

Examples:

* "Check case 04210225 and CSB-7587"

---

## 4. 📊 SBR Filtering

Trigger: `search_cases`

Examples:

* "Show Messaging cases"
* "List RHOAI issues"

---

## 5. 💬 General Queries

Trigger: LLM only

Examples:

* "What products does Red Hat support?"

---

# 🛠️ Setup & Installation

## 1. Clone Repo

```bash
git clone https://github.com/your-repo/ChatBot_MCP
cd ChatBot_MCP
```

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Configure Environment Variables

Create `.env`:

```bash
TOKEN=your_red_hat_api_token
USER_KEY=your_llm_api_key
MODEL_API=your_llm_endpoint
EMAIL=your_redhat_email
JIRA_TOKEN=your_jira_token
```

---

## 4. Run Application

```bash
# Terminal 1
python salesforce_server.py

# Terminal 2
python app.py
```

---

# 📖 Usage Examples

### 🔍 Case Deep Dive

```
What is the progress on case 04206670?
```

---

### 🔗 Jira Analysis

```
Summarize CEQ-12628
```

---

### 🔄 Hybrid

```
Check case 04206670 and related Jira
```

---

### 📊 Monitoring

```
Show Messaging cases
```

---

# ⚙️ Technical Highlights

### Jira API (GET Request)

```bash
curl -u "$EMAIL:$JIRA_TOKEN" \
  -H "Accept: application/json" \
  https://redhat.atlassian.net/rest/api/3/issue/CSB-7587
```

---

### ADF Parsing

* Converts Jira rich text → plain text
* Handles:

  * paragraphs
  * mentions
  * lists
  * code blocks

---

### Robust Error Handling

* Detects:

  * Permission issues
  * Empty responses
  * Invalid Jira keys
* Prevents broken UI rendering

---

# ✅ Summary

This system provides:

* End-to-end **case + Jira intelligence**
* Clean, **deterministic UI output**
* Real-time **engineering visibility**
* Scalable MCP-based architecture

---

If you want next level upgrade, I can help you add:

* 🔴 Priority highlighting (Critical / Major)
* 📈 Case aging / SLA tracking
* 🤖 Auto escalation detection
* 📊 Dashboard UI (React / Streamlit)

Just tell me 👍

