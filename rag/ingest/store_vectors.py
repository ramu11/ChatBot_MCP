import json
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

# ----------------------------
# PATH CONFIG
# ----------------------------
CHUNKS_ROOT = Path("rag/chunks")
VECTOR_DB_DIR = Path("rag/vector_store")

# ----------------------------
# INITIALIZE CHROMA DB
# ----------------------------
# Using PersistentClient so the database saves to your disk directory
chroma_client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))

# Choose an embedding function. 
# For a free, local setup, sentence-transformers runs entirely on your machine.
# Swap to OpenAIEmbeddingFunction if you prefer cloud models.
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# Create or fetch your RAG collection
collection = chroma_client.get_or_create_collection(
    name="redhat_docs_collection",
    embedding_function=embedding_function,
    metadata={"hnsw:space": "cosine"} # Cosine distance is excellent for text matching
)

# ----------------------------
# PROCESSING UTILITY
# ----------------------------
def load_and_store_chunks(json_file: Path):
    print(f"[INFO] Reading chunks from: {json_file}")
    
    with open(json_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)
        
    if not chunks:
        print(f"[WARN] No chunks found in {json_file.name}")
        return

    # Chroma expects parallel lists for batch insertions
    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        ids.append(chunk["id"])
        documents.append(chunk["content"])
        
        # Flatten metadata fields to ensure strict compatibility with database constraints
        meta = chunk["metadata"]
        flat_meta = {
            "product": meta["product"],
            "version": meta["version"],
            "guide": meta["guide"],
            "section": meta["section"],
            "chunk_type": meta["chunk_type"],
            "source_file": meta["source_file"],
            "chunk_index": int(meta["chunk_index"])
        }
        metadatas.append(flat_meta)

    # Batch upsert to the vector database
    # Chroma handles slicing automatically, but small batches (e.g., 500) prevent memory spikes
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i+batch_size],
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size]
        )
        
    print(f"[SUCCESS] Indexed {len(ids)} chunks from {json_file.name}")

# ----------------------------
# PIPELINE EXECUTION
# ----------------------------
def populate_vector_store():
    # Find all generated chunk json files
    chunk_files = list(CHUNKS_ROOT.rglob("*_chunks.json"))
    
    if not chunk_files:
        print("[INFO] No chunk JSON files discovered. Run chunk_markdown.py first.")
        return

    print(f"[INFO] Found {len(chunk_files)} chunk files to index.")

    for chunk_file in chunk_files:
        try:
            load_and_store_chunks(chunk_file)
        except Exception as e:
            print(f"[ERROR] Failed indexing {chunk_file.name}: {e}")

    print(f"[INFO] Vector database generation complete. Total entries: {collection.count()}")

if __name__ == "__main__":
    populate_vector_store()
