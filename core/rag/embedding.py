from config.settings import settings

_model = None


def get_embedding_model():
    global _model

    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)

    return _model


def embed_text(text: str):
    model = get_embedding_model()
    embedding = model.encode(text)
    return embedding.tolist()
