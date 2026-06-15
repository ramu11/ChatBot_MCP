ChatBot_MCP

Red Hat Support Assistant (MCP Edition)

An intelligent support agent that leverages the Model Context Protocol (MCP) to fetch and analyze Red Hat support cases, enrich them with Jira data, and generate concise technical summaries using an LLM.

---

Features

Logic 1: Deep Case Analysis (Triple-Scan)

Automatically triggers a full scan when an 8-digit case ID is detected:

- Case Details 
- Case Comments
- External Tracker Updates

This ensures no Jira reference is missed.

---

Logic 2: Direct Jira Enrichment

When a Jira ID (e.g., CSB-7587) is detected:

- Calls Jira MCP tool (get_jira_details)
- Fetches:
- Status
- Summary
- Priority
- Components / Versions
- Jira comments (ADF to plain text)

---

Logic 3: Intelligent Filtering

Supports filtering of active cases:

- Status:
- Waiting on Red Hat
- Waiting on Engineering
- Waiting on Customer
- SBR filtering (e.g., Messaging, RHOAI)

---

Logic 4: Chronological Priority

- Server-side sorting by lastModifiedDate
- Always shows latest updates first

---

Logic 5: Hybrid Query Handling

Handles:

- Case only
- Jira only
- Case + Jira
- No Jira scenarios
- General queries

---

Logic 6: Deterministic Rendering

- Clean horizontal tables
- Consistent structure (no broken markdown)
- Jira IDs rendered as clickable links

---

Logic 7: Clickable Jira Links

- Jira IDs rendered as hyperlinks

---

Logic 8: Engineering Insights (Jira Comment Summary)

- Extracts Jira comments
- Converts ADF to plain text
- Displays summarized insights

---

Logic 9: AI-Powered Documentation Search (RAG)

Adds intelligent retrieval from official Red Hat documentation:

- Detects documentation-related queries automatically
- Identifies product (Kafka, AMQ, etc.)
- Retrieves relevant content from vector database
- Sends grounded context to LLM for accurate responses

Examples:

- search official kafka docs
- amq broker documentation

---

AI Architecture

The system follows a production-grade layered AI design:

Agent Layer
- Handles deterministic workflows (Case, Jira)
- Routes general queries to AI pipeline

Intent Router
- Detects query intent
- Routes docs queries to RAG and general queries to LLM

Product Detection
- Maps query to product
- Kafka to red_hat_streams_for_apache_kafka
- AMQ to red_hat_amq_broker

RAG Handler
- Retrieves top-k relevant chunks from vector DB
- Prepares context for LLM grounding

Vector Store
- Persistent storage using ChromaDB
- Embeddings via BGE-M3
- Supports semantic search

Ingestion Layer
- Red Hat crawler for structured ingestion
- Generic ingestion for files and URLs

---

RAG Pipeline Flow

Query to Intent Detection to Product Detection to Vector Search to Context to LLM to Answer

---

Project Structure

Frontend and Entry

app.py
- Flask web server
- Manages chat sessions
- Defines tool manifest

---

Orchestration

agent.py
- Regex detection for Case ID and Jira ID
- Executes workflow:
- Case to Triple Scan
- Jira to Direct fetch
- Docs to RAG pipeline
- Builds Jira tables and engineering insights
- Handles tool responses and AI routing

llm.py
- Connects to LLM
- Generates summaries and RAG responses

---

AI Pipeline

intent_router.py
- Detects intent and product

docs_handler.py
- Retrieves documentation chunks
- Prepares context

---

RAG Layer

vector_store.py
- Persistent storage
- Embedding and retrieval

redhat_crawler.py
- Crawls documentation
- Extracts clean text
- Stores metadata

ingest_docs.py
- Ingests files and URLs

---

Tooling Layer

salesforce_server.py
- Fetches case details and comments
- Integrates Jira API
- Returns structured JSON

tool_router.py
- Routes tool calls securely

---

Query Patterns

Salesforce Case Queries
Trigger: Triple Scan

Direct Jira Queries
Trigger: Jira API

Hybrid Queries
Trigger: Case and Jira

SBR Filtering
Trigger: search_cases

General Queries
Trigger: LLM

Documentation Queries
Trigger: RAG pipeline

Examples:

- official kafka docs
- amq broker documentation

---

Setup and Installation

Clone repository

git clone https://github.com/your-repo/ChatBot_MCP
cd ChatBot_MCP

Install dependencies

pip install -r requirements.txt

Configure environment variables

TOKEN=your_red_hat_api_token
USER_KEY=your_llm_api_key
MODEL_API=your_llm_endpoint
EMAIL=your_redhat_email
JIRA_TOKEN=your_jira_token

Run application

python salesforce_server.py
python app.py

---

Usage Examples

Case Deep Dive
What is the progress on case 04206670

Jira Analysis
Summarize CEQ-12628

Hybrid
Check case 04206670 and related Jira

Monitoring
Show Messaging cases

Documentation Search
search official kafka docs

---

Technical Highlights

Jira API
GET /rest/api/3/issue/{jira_id}

ADF Parsing
Converts Jira rich text to plain text

Vector Search
Semantic search using embeddings
Persistent storage via ChromaDB

Robust Error Handling
Handles permission issues, empty responses, invalid keys

---

Summary

This system provides:

- Case and Jira intelligence
- AI-powered documentation search
- Clean deterministic outputs
- Real-time engineering insights
- Modular production-grade architecture

---

Future Enhancements

- Product-based filtering in RAG
- Reranking for better retrieval accuracy
- Source citation in responses
- Advanced intent detection
- Dashboard UI

---

 next level upgrade is:

- Priority highlighting
- SLA tracking
- Auto escalation detection
- Dashboard UI

---
