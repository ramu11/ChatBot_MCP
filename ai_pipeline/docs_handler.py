# ai_pipeline/docs_handler.py
import os
import sys
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

# ---------------------------------------------------------
# PATH CONFIG (Matches store_vectors.py)
# ---------------------------------------------------------
VECTOR_DB_DIR = Path("rag/vector_store")

# ---------------------------------------------------------
# KEYWORD PRODUCT ROUTER
# ---------------------------------------------------------
# Define keywords that should explicitly trigger RAG exploration
RAG_KEYWORDS = [
    "kafka",
    "amq",
    "artemis",
    "streams",
    "kraft",
    "zookeeper",
    "strimzi",
    "openshift",
]


def is_rag_applicable(query: str) -> bool:
    """
    Scans the query for specific Red Hat product keywords.
    """
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in RAG_KEYWORDS)


# ---------------------------------------------------------
# EXECUTE VECTOR SEARCH
# ---------------------------------------------------------
def handle_docs_query(query: str, product: str = None) -> str:
    """
    Main entry point for the agent's RAG flow.
    Ensures safe fallbacks so the agent pipeline never crashes.
    """
    # Step 1: Determine whether RAG should be attempted.
    # If the classifier already identified a supported product,
    # trust that decision. Otherwise, fall back to keyword routing.

    if product:
        sys.stderr.write(f"[RAG Router] Product detected by classifier: {product}\n")
    elif not is_rag_applicable(query):
        sys.stderr.write(
            "[RAG Router] Query not related to targeted products. Skipping RAG.\n"
        )
        return ""
    # Step 2: Defensive check for existing database
    if not VECTOR_DB_DIR.exists():
        sys.stderr.write(
            f"[RAG Error] Vector database directory not found at {VECTOR_DB_DIR}. Falling back.\n"
        )
        return ""

    try:
        # Initialize client and match configuration from store_vectors.py
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))

        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        # Pull collection safely
        collection = chroma_client.get_collection(
            name="redhat_docs_collection", embedding_function=embedding_function
        )

        # ai_pipeline/docs_handler.py (Excerpt update around line 68)

        # Query database for matching segments
        sys.stderr.write(f"[RAG Execute] Searching knowledge base for: '{query}'\n")
        results = collection.query(
            query_texts=[query],
            n_results=10,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],  # Include distances for threshold filtering
        )

        if not results or not results.get("documents") or not results["documents"][0]:
            sys.stderr.write("[RAG Result] Vector match space returned empty.\n")
            return ""

        context_chunks = []
        # Distance threshold (adjust based on your embedding model, typically < 0.8 for MiniLM)
        RELEVANCE_THRESHOLD = 0.85

        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            if dist > RELEVANCE_THRESHOLD:
                continue  # Skip low-relevance matches

            header = f"--- Source: {meta.get('guide', 'Unknown Guide')} | Section: {meta.get('section', 'Top')} ---"
            context_chunks.append(f"{header}\n{doc}")

        if not context_chunks:
            sys.stderr.write("[RAG Result] No chunks passed the relevance threshold.\n")
            return ""

        return "\n\n".join(context_chunks)

    except Exception as e:
        # CRITICAL GUARDRAIL: Catch database/embedding issues and log instead of crashing
        sys.stderr.write(f"[RAG Critical Exception Fail-Safe] Error: {str(e)}\n")
        return ""
