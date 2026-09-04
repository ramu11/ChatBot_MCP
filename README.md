Here is the updated `README.md` file. All formatting, structure, sections, and ASCII diagrams have been preserved, with updates added for multi-entity batch processing, context-aware follow-up summarization without duplicate search loops, and Jira deduplication.

```markdown
# ChatBot_MCP

A modular, intent-aware AI Support Assistant built with Python and Flask, utilizing the **Model Context Protocol (MCP)** to interact with enterprise systems (Salesforce and Jira), local RAG documentation repositories, and an evidence-based historical case investigation engine.

---

##  Architectural Overview


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

```

---

## ⚙️ Deterministic Intent Evaluation Pipeline

Incoming queries are evaluated through a strict 5-stage deterministic priority pipeline before falling back to zero-shot LLM intent classification:


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

```

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

##  Execution Flows & Diagrams

### 1. Investigation Flow (`investigation`)

* **Trigger:** Query contains explicit search verbs (`"list cases"`, `"find tickets"`), incident/failure terms (`"oom"`, `"crash"`), product + failure combinations, or zero-shot LLM classification.
* **Follow-up Interception:** Subsequent queries like `"summarize all above cases"` or `"summarize these cases"` are intercepted directly from session history (`messages`) by `investigation_engine.py`, synthesizing root cause analysis without re-executing search tool calls.
* **Context Protection:** Context history resolution is explicitly locked out when `request_mode == "investigation"` unless a follow-up summarization keyword is detected.
* **Execution:**

1. `investigation_engine.py` cleans input text (stripping digests, container SHAs, logs).
2. Executes historical case retrieval via MCP `search_historical_cases`.
3. Applies `normalize_linked_resource` to rewrite raw API endpoints (`/hydra/rest/drupal/solutions/123456`) into clean public customer Knowledgebase URLs (`https://access.redhat.com/solutions/123456`).
4. Generates an evidence-based report (Pass 1 Case Listing with plain-text prompt guidance / Pass 2 Context Synthesis).


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
   ├── 4. Normalize solution URLs -> [https://access.redhat.com/solutions/](https://access.redhat.com/solutions/)<ID>
   └── 5. LLM Pass 1 Listing with Tip: 'summarize all above cases'
   │
   ▼
Structured Report Output to User

```

---

### 2. Salesforce Case Lookup Flow (`case_lookup`)

* **Trigger:** An 8-digit numerical ID (e.g., `12345678`) is detected in the query or extracted during single-entity follow-ups. Multiple case IDs trigger parallel batch evaluation.
* **Execution:**

1. Single Case: Invokes MCP tools `get_support_case` and `list_case_comments`. Multi-Case: Invokes `batch_fetch_cases` using parallel `ThreadPoolExecutor`.
2. Scans case descriptions and comments via regex for cross-referenced Jira keys (e.g., `ABC-xxxx` or `XYZ-123`).
3. Explicitly deduplicates Jira keys and batch-fetches each unique key once.
4. Sanitizes output via `sanitize_payload_data` and builds a structured summary with a Markdown Jira reference table.


User Input ("get case 12345678")
   │
   ▼
request_classifier.py ──► Priority 1 Match: case_id = "12345678" (mode: "case_lookup")
   │
   ▼
agent.py
   ├── 1. Call MCP: get_support_case("04206670") & list_case_comments("12345678")
   ├── 2. Scan case text for Jira keys (\b[A-Z]{2,10}-[0-9]+\b)
   ├── 3. Deduplicate Jira keys & batch-fetch unique keys ONCE
   ├── 4. Sanitize payloads (redact SHAs, secrets, IPs, and system paths)
   └── 5. LLM generates Case Summary + Markdown Jira Metadata Table
   │
   ▼
Rendered Case + Jira Report

```

---

### 3. Jira Issue Lookup Flow (`jira_lookup`)

* **Trigger:** A project key + issue number (e.g., `ABC-1234`) is present in the prompt. Multiple Jira keys trigger parallel batch evaluation (`summarize_and_evaluate_jiras`).
* **Execution:**

1. Invokes MCP tools `jira.get_issue` and `jira.get_comments`.
2. Redacts sensitive parameters via `sanitize_payload_data`.
3. Passes sanitized payload to `ask_llm` to extract issue status, problem pattern, customer impact, engineering analysis, and next steps.
4. Formats a structured Jira detail table at the bottom of the response.


User Input ("show jira ABC-1234")
   │
   ▼
request_classifier.py ──► Priority 2 Match: jira_key = "ABC-1234" (mode: "jira_lookup")
   │
   ▼
agent.py
   ├── 1. Call MCP: jira.get_issue("ABC-1234")
   ├── 2. Call MCP: jira.get_comments("ABC-1234")
   ├── 3. Sanitize raw JSON payloads
   └── 4. LLM generates Analysis + Formatted Markdown Table
   │
   ▼
Rendered Jira Analysis & Status Table

```

---

### 4. General / Conditional RAG Flow (`general`)

* **Trigger:** How-to questions, pre-upgrade guides, syntax explanations, or queries without incident indicators.
* **Execution:**

1. Checks for product match via `detect_product`.
2. If a product matches, calls `docs_handler.py` to search local repository documentation.
3. **Documentation Found:** Formulates a RAG prompt (`RAG_DOCS`) injecting local context.
4. **No Documentation / Out-of-Scope:** Defaults to core model knowledge (`CORE_KB`) while enforcing strict system boundary constraints (e.g., declining non-technical or geopolitical topics).


User Input ("how to upgrade amq streams on openshift?")
   │
   ▼
request_classifier.py ──► mode: "general", product: "red_hat_streams_for_apache_kafka"
   │
   ▼
agent.py ──► docs_handler.py
   ├── 1. Search local documentation repository for matching product docs
   ├── 2. [MATCH FOUND]: Inject local context ──► ask_llm (Prompt Mode: RAG_DOCS)
   └── 3. [NO MATCH / OUT OF SCOPE]: Direct LLM synthesis ──► ask_llm (Prompt Mode: CORE_KB)
   │
   ▼
Technical Guidance Response

```

---

##  Architectural Highlights & Safety Features

1. **Deterministic Intent Authority:** Regex and heuristic keyword matching take precedence over LLM classification to reduce token overhead, minimize execution latency, and ensure strict deterministic routing.
2. **Context-Aware Follow-Up Summarization:** Detects summarization queries over previously retrieved historical case listings directly from conversation memory (`session["history"]`), bypassing redundant search tool execution.
3. **Multi-Entity Parallel Processing & Jira Deduplication:** Supports parallel candidate processing for multi-case and multi-Jira workflows while enforcing deduplication on extracted Jira keys to prevent double API invocations.
4. **Context-History Isolation:** The agent prevents stale conversation memory (e.g., a previously discussed Jira ticket ID) from hijacking fresh search or investigation queries.
5. **URL Normalization:** Raw backend storage or API URLs returned by internal search engines are automatically rewritten to public-facing customer Knowledgebase endpoints before presentation.
6. **Network Guardrails:** Low-level network exceptions (e.g., DNS resolution failures or gateway timeouts) are caught in the HTTP execution layer (`llm.py`), preventing stack traces from leaking into the user interface.

---
