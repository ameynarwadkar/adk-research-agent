import pickle
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

# Load BM25
try:
    with open("data/bm25_index.pkl", "rb") as f:
        bm25 = pickle.load(f)
    with open("data/bm25_docs.pkl", "rb") as f:
        bm25_docs = pickle.load(f)
except Exception:
    bm25 = None
    bm25_docs = []

# Load Dense
try:
    dense_model = SentenceTransformer("BAAI/bge-base-en-v1.5")
    qdrant = QdrantClient(path="data/qdrant")
except Exception:
    dense_model = None
    qdrant = None


@observe()
def search_bm25(query: str, k=10):
    if not bm25: return []
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)
    top_indices = scores.argsort()[-k:][::-1]
    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            doc = bm25_docs[idx].copy()
            doc["score"] = scores[idx]
            results.append(doc)
    return results

@observe()
def search_dense(query: str, k=10):
    if not qdrant or not dense_model: return []
    vector = dense_model.encode(query).tolist()
    try:
        response = qdrant.query_points(
            collection_name="eu_regs",
            query=vector,
            limit=k
        )
        return [{"score": res.score, **res.payload} for res in response.points]
    except Exception as e:
        print(f"Error searching Qdrant: {e}")
        return []

@observe()
def hybrid_search(query: str, k=10, c=60):
    bm25_results = search_bm25(query, k=k)
    dense_results = search_dense(query, k=k)
    
    rrf_scores = {}
    docs_by_id = {}
    
    for rank, doc in enumerate(bm25_results):
        doc_id = f"{doc['doc_id']}_{doc['article_number']}"
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rank + 1 + c)
        docs_by_id[doc_id] = doc
        
    for rank, doc in enumerate(dense_results):
        doc_id = f"{doc['doc_id']}_{doc['article_number']}"
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rank + 1 + c)
        docs_by_id[doc_id] = doc
        
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    final_results = []
    for doc_id, score in sorted_docs[:k]:
        doc = docs_by_id[doc_id]
        doc["rrf_score"] = score
        final_results.append(doc)
        
    return final_results
