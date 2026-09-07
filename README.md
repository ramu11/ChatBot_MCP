# ChatBot_MCP

A modular, intent-aware AI Support Assistant built with Python and Flask, utilizing the **Model Context Protocol (MCP)** to interact with enterprise systems (Salesforce and Jira), local RAG documentation repositories, and an evidence-based historical case investigation engine.

---

## 🏗️ Architectural Overview

<pre>
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
                               |          Agent Orchestrator       |
                               |             (agent.py)            |
                               +-----------------------------------+
                                                 |
         +---------------------------------------+---------------------------------------+
         |                                       |                                       |
         v                                       v                                       v
+-----------------------+               +-----------------------+               +-----------------------+
|   AI Pipeline Module  |               |     LLM Interface     |               |     Tool Router       |
| (ai_pipeline/)        |               |       (llm.py)        |               | (tools/tool_router.py)|
| - request_classifier  |               +-----------------------+               +-----------------------+
| - investigation_engine|                           |                                       |
| - docs_handler        |                           v                                       v
| - keywords            |               +-----------------------+               +-----------------------+
+-----------------------+               |   OpenAI-Compatible   |               |       MCP Client      |
                                        |      API Endpoint     |               | (tools/mcp_client.py) |
                                        +-----------------------+               +-----------------------+
                                                                                            |
                                                                                            v
                                                                                +-----------------------+
                                                                                |  Salesforce / Jira    |
                                                                                |    MCP Servers        |
                                                                                +-----------------------+
</pre>

### ⚙️ Deterministic Intent Evaluation Pipeline

Incoming queries are evaluated through a strict 5-stage deterministic priority pipeline before falling back to zero-shot LLM intent classification:

<pre>
                  Incoming User Request String
                               |
                               v
         +-------------------------------------------+
         | Priority 1: Salesforce Case ID Regex      |
         |           (\b\d{8}\b)                     |
         +-------------------------------------------+
           | YES                                | NO
           v                                    v
  [mode = case_lookup]         +-------------------------------------------+
                               | Priority 2: Jira Key Regex                |
                               |      (\b[A-Z]{2,10}-[0-9]+\b)             |
                               +-------------------------------------------+
                                 | YES                                | NO
                                 v                                    v
                        [mode = jira_lookup]         +-------------------------------------------+
                                                     | Priority 3: Product Detection             |
                                                     |       (PRODUCT_CATALOG)                   |
                                                     +-------------------------------------------+
                                                                          |
                                                                          v
                                                     +-------------------------------------------+
                                                     | Priority 4: Investigation / Failure Terms |
                                                     |      (is_investigation Heuristics)        |
                                                     +-------------------------------------------+
                                                       | YES                                | NO
                                                       v                                    v
                                              [mode = investigation]       +-------------------------------------------+
                                                                           | Priority 5: Zero-Shot LLM Fallback        |
                                                                           |     (CLASSIFIER_PROMPT)                   |
                                                                           +-------------------------------------------+
                                                                             |                       |
                                                                             v                       v
                                                                   [mode = investigation]     [mode = general]
</pre>

---

## 🛠️ Component Breakdown

| Module | File | Description |
| --- | --- | --- |
| **App Layer** | `app.py` | Flask web application managing chat HTTP routing, filesystem sessions, and request lifetimes. |
| **Agent Orchestrator** | `agent.py` | Core workflow orchestrator executing intent classification, context-history isolation, single vs. parallel multi-entity routing, payload sanitization, and output table formatting. |
| **AI Classifier** | `ai_pipeline/request_classifier.py` | Enforces the 5-stage priority routing pipeline (`case_lookup`, `jira_lookup`, `investigation`, `general`) and extracts candidate lists for multi-entity resolution. |
| **Keywords Catalog** | `ai_pipeline/keywords.py` | Product catalog mappings, investigation verbs (`"list cases"`, `"search tickets"`), failure terms, and normalization rules. |
| **Investigation Engine** | `ai_pipeline/investigation_engine.py` | Handles multi-pass historical case search via MCP, intercepts context follow-up requests (`"summarize all above cases"`) directly from history, normalizes URLs, and builds structured diagnostic summaries. |
| **Docs RAG Handler** | `ai_pipeline/docs_handler.py` | Fetches local markdown/text documentation context for RAG enrichment when queries fall under `general` mode. |
| **LLM Interface** | `llm.py` | Low-level client managing sandboxing, Pass 1 case list formatting, prompt-injection isolation, raw API network exception handling, and Knowledgebase URL normalization. |
| **Tools & MCP Router** | `tools/tool_router.py` | Bridges backend execution functions with direct MCP tool bindings. |
| **Jira Adapter** | `tools/jira_adapter.py` | Provides deduplicated Jira extraction, single and batch parallel Jira fetching, and Markdown table synthesis formatting. |
| **MCP Client** | `tools/mcp_client.py` | Implements Model Context Protocol handling for remote Salesforce and Jira enterprise servers. |

---

## 🔄 Execution Flows & Diagrams

### 1. Investigation Flow (`investigation`)

* **Trigger:** Query contains explicit search verbs (`"list cases"`, `"find tickets"`), incident/failure terms (`"oom"`, `"crash"`), product + failure combinations, or zero-shot LLM classification.
* **Follow-up Interception:** Subsequent queries like `"summarize all above cases"` or `"summarize these cases"` are intercepted directly from session history (`messages`) by `investigation_engine.py`, synthesizing root cause analysis without re-executing search tool calls.
* **Context Protection:** Context history resolution is explicitly locked out when `request_mode == "investigation"` unless a follow-up summarization keyword is detected.
* **Execution Steps:**
  1. `investigation_engine.py` cleans input text (stripping digests, container SHAs, logs).
  2. Executes historical case retrieval via MCP `search_historical_cases`.
  3. Applies `normalize_linked_resource` to rewrite raw API endpoints (`/hydra/rest/drupal/solutions/123456`) into clean public customer Knowledgebase URLs (`[https://access.redhat.com/solutions/123456](https://access.redhat.com/solutions/123456)`).
  4. Generates an evidence-based report (Pass 1 Case Listing with plain-text prompt guidance / Pass 2 Context Synthesis).

<pre>
User Input ("list kafka cert related cases")
   │
   ▼
request_classifier.py ──► mode: "investigation", product: "red_hat_streams_for_apache_kafka"
   │
   ▼
agent.py (Passes session history matrix)
   │
   ▼
investigation_engine.py
   ├── 1. Check if query is a follow-up ("summarize all above cases") ──► [IF YES]: Synthesize history directly
   ├── 2. [IF NO]: Clean query text & extract failure terms
   ├── 3. Call MCP search_historical_cases tool
   ├── 4. Normalize solution URLs -> [https://access.redhat.com/solutions/&lt;ID&gt](https://access.redhat.com/solutions/&lt;ID&gt);
   └── 5. LLM Pass 1 Listing with Tip: 'summarize all above cases'
   │
   ▼
Structured Report Output to User
</pre>
