# ai_pipeline/docs_handler.py
"""
Documentation Handler Module for RAG (Retrieval-Augmented Generation).

This module manages document retrieval for general product queries (Flow 3).
It uses LangChain with a local ChromaDB vector store powered by BGE-Small-EN-v1.5
embeddings to fetch relevant documentation chunks based on detected products or keywords.
"""

import sys
from pathlib import Path
from typing import List, Optional

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Import central product catalog and keywords from keywords.py
from ai_pipeline.keywords import PRODUCT_CATALOG

# ---------------------------------------------------------
# PATH & COLLECTION CONFIG
# ---------------------------------------------------------
VECTOR_DB_DIR = Path("rag/vector_store")
COLLECTION_NAME = "redhat_docs_collection"


# ---------------------------------------------------------
# DYNAMIC KEYWORD ROUTER FUNCTIONS
# ---------------------------------------------------------
def _extract_all_rag_keywords() -> List[str]:
    """
    Extracts and flattens all product keywords from the central catalog.

    Iterates through PRODUCT_CATALOG in keywords.py to build a unified list
    of lowercase product keywords used for initial RAG applicability checks.

    Returns:
        List[str]: A unique list of lowercase product keyword strings.
    """
    all_keywords = set()
    for product_info in PRODUCT_CATALOG.values():
        for kw in product_info.get("keywords", []):
            all_keywords.add(kw.lower().strip())
    return list(all_keywords)


# Dynamically loaded set of product keywords
RAG_KEYWORDS = _extract_all_rag_keywords()


def is_rag_applicable(query: str) -> bool:
    """
    Evaluates whether a user query is eligible for RAG document retrieval.

    Scans the raw query against the catalog-derived RAG_KEYWORDS list.

    Args:
        query (str): The raw incoming user query string.

    Returns:
        bool: True if at least one product keyword is found, False otherwise.
    """
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in RAG_KEYWORDS)


# ---------------------------------------------------------
# LANGCHAIN VECTOR STORE INITIALIZATION
# ---------------------------------------------------------
def get_vector_store() -> Optional[Chroma]:
    """
    Initializes and connects to the persistent LangChain Chroma vector store.

    Uses BAAI/bge-small-en-v1.5 embeddings with normalized outputs to ensure
    consistent cosine similarity scoring.

    Returns:
        Optional[Chroma]: An active LangChain Chroma vector store instance,
                          or None if initialization fails or directory missing.
    """
    # Guardrail: Ensure vector store path exists before initializing client
    if not VECTOR_DB_DIR.exists():
        sys.stderr.write(
            f"[RAG Error] Vector database directory not found at {VECTOR_DB_DIR}.\n"
        )
        return None

    try:
        # BGE-small-en-v1.5 Embedding Initialization via LangChain
        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={
                "normalize_embeddings": True
            },  # Essential for BGE cosine distance
        )

        # Connect to existing persistent ChromaDB directory
        vector_store = Chroma(
            client_settings=None,
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(VECTOR_DB_DIR),
        )
        return vector_store

    except Exception as e:
        sys.stderr.write(
            f"[RAG Error] Failed to initialize LangChain Chroma store: {str(e)}\n"
        )
        return None


# ---------------------------------------------------------
# EXECUTE VECTOR SEARCH
# ---------------------------------------------------------
def handle_docs_query(query: str, product: Optional[str] = None) -> str:
    """
    Main entry point for executing Flow 3 (RAG Documentation Search).

    1. Checks if RAG applies based on product detection or keyword presence.
    2. Queries ChromaDB for top similarity matches.
    3. Filters out low-relevance documents using a cosine distance threshold.
    4. Formats and returns passed chunks as a single context string.

    Args:
        query (str): The user query string.
        product (Optional[str]): Product identifier if pre-detected by request classifier.

    Returns:
        str: Formatted documentation context text with section headers,
             or an empty string if no relevant docs pass threshold/errors occur.
    """
    # Step 1: Check eligibility
    if product:
        sys.stderr.write(f"[RAG Router] Product detected by classifier: {product}\n")
    elif not is_rag_applicable(query):
        sys.stderr.write(
            "[RAG Router] Query not related to targeted products. Skipping RAG.\n"
        )
        return ""

    # Step 2: Load Vector Store instance
    vector_store = get_vector_store()
    if not vector_store:
        return ""

    try:
        sys.stderr.write(
            f"[RAG Execute] Searching LangChain vector store for: '{query}'\n"
        )

        # Distance threshold (Cosine distance for BGE; < 0.40 indicates high relevance)
        DISTANCE_THRESHOLD = 0.40

        # Perform similarity search with score via LangChain
        results_with_scores = vector_store.similarity_search_with_score(query, k=10)

        if not results_with_scores:
            sys.stderr.write("[RAG Result] Vector match space returned empty.\n")
            return ""

        context_chunks = []
        for doc, distance in results_with_scores:
            # Skip chunks that exceed the maximum allowed distance threshold
            if distance > DISTANCE_THRESHOLD:
                continue

            meta = doc.metadata or {}
            guide = meta.get("guide", "Unknown Guide")
            section = meta.get("section", "Top")

            # Format chunk header for LLM context injection
            header = f"--- Source: {guide} | Section: {section} ---"
            context_chunks.append(f"{header}\n{doc.page_content}")

        if not context_chunks:
            sys.stderr.write("[RAG Result] No chunks passed the relevance threshold.\n")
            return ""

        return "\n\n".join(context_chunks)

    except Exception as e:
        # CRITICAL FAIL-SAFE: Prevent vector execution errors from breaking overall pipeline
        sys.stderr.write(f"[RAG Critical Exception Fail-Safe] Error: {str(e)}\n")
        return ""
