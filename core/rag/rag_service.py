from .embedding import embed_text
from .vector_store import vector_store


def split_text(text, chunk_size=300):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end

    return chunks


def add_document_to_rag(text):
    chunks = split_text(text)
    embeddings = []

    for chunk in chunks:
        emb = embed_text(chunk)
        embeddings.append(emb)

    if embeddings:
        vector_store.add_embeddings(embeddings, chunks)


def retrieve_docs(question, k=3):
    if not vector_store.has_embeddings():
        return []

    q_emb = embed_text(question)
    return vector_store.search(q_emb, k)


def retrieve_docs_with_scores(question, k=3):
    if not vector_store.has_embeddings():
        return []

    q_emb = embed_text(question)
    return vector_store.search_with_scores(q_emb, k)
