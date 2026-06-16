import faiss
import numpy as np


class VectorStore:
    def __init__(self, dim=512):
        self.index = faiss.IndexFlatL2(dim)
        self.texts = []
        self.metadata = []

    def clear(self):
        self.index = faiss.IndexFlatL2(self.index.d)
        self.texts = []
        self.metadata = []

    def has_embeddings(self):
        return self.index.ntotal > 0

    def add_embeddings(self, embeddings, texts, metadata=None):
        embeddings = np.array(embeddings).astype("float32")
        self.index.add(embeddings)
        self.texts.extend(texts)
        if metadata is None:
            metadata = [{} for _ in texts]
        self.metadata.extend(metadata)

    def search(self, query_embedding, k=3):
        results = self.search_with_scores(query_embedding, k)
        return [item["text"] for item in results]

    def search_with_scores(self, query_embedding, k=3):
        if not self.has_embeddings():
            return []

        query_embedding = np.array([query_embedding]).astype("float32")
        distances, indices = self.index.search(query_embedding, k)
        results = []

        for rank, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.texts):
                item_metadata = self.metadata[idx] if idx < len(self.metadata) else {}
                results.append(
                    {
                        "rank": rank + 1,
                        "text": self.texts[idx],
                        "score": float(distances[0][rank]),
                        **item_metadata,
                    }
                )

        return results


vector_store = VectorStore()
