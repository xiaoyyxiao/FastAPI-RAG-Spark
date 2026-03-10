import faiss
import numpy as np
# 向量数据库

class VectorStore:

    def __init__(self, dim=512):
        # FAISS向量索引
        self.index = faiss.IndexFlatL2(dim)
        self.texts = []

    def add_embeddings(self, embeddings, texts):

        embeddings = np.array(embeddings).astype("float32")

        self.index.add(embeddings)

        self.texts.extend(texts)

    def search(self, query_embedding, k=3):
        query_embedding = np.array([query_embedding]).astype("float32")
        D, I = self.index.search(query_embedding, k)
        results = []
        
        for idx in I[0]:
            # 【关键修改】：增加 idx >= 0 的判断，过滤掉 FAISS 返回的 -1
            if idx >= 0 and idx < len(self.texts):
                results.append(self.texts[idx])
                
        return results


# 全局实例
vector_store = VectorStore()