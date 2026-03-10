from .embedding import embed_text
from .vector_store import vector_store


def split_text(text, chunk_size=300):
    """
    文本切块
    """
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end

    return chunks


def add_document_to_rag(text):
    """
    文档进入知识库
    """

    chunks = split_text(text)

    embeddings = []

    for chunk in chunks:
        emb = embed_text(chunk)
        embeddings.append(emb)

    vector_store.add_embeddings(embeddings, chunks)


def retrieve_docs(question, k=3):
    """
    检索相关文档
    """

    q_emb = embed_text(question)

    docs = vector_store.search(q_emb, k)

    return docs