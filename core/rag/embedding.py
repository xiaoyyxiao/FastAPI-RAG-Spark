from sentence_transformers import SentenceTransformer

# 中文向量模型（效果很好）
model = SentenceTransformer("BAAI/bge-small-zh")

def embed_text(text: str):
    """
    生成文本向量
    """
    embedding = model.encode(text)
    return embedding.tolist()