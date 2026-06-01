import faiss
import numpy as np


class VectorStore:
    def __init__(self, dim=512):
        self.index = faiss.IndexFlatL2(dim)
        self.texts = []

    def has_embeddings(self):
        return self.index.ntotal > 0

    def add_embeddings(self, embeddings, texts):
        embeddings = np.array(embeddings).astype("float32")
        self.index.add(embeddings)
        self.texts.extend(texts)

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
                results.append(
                    {
                        "rank": rank + 1,
                        "text": self.texts[idx],
                        "score": float(distances[0][rank]),
                    }
                )

        return results


vector_store = VectorStore()
