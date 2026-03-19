import chromadb
from sentence_transformers import SentenceTransformer

client = chromadb.Client()
collection = client.get_or_create_collection("docs")

model = SentenceTransformer("all-MiniLM-L6-v2")

def search_docs(query):

    emb = model.encode(query).tolist()

    result = collection.query(
        query_embeddings=[emb],
        n_results=3
    )

    return result["documents"][0]
