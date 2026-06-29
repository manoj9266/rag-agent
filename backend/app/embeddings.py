from langchain_core.embeddings import Embeddings

from app.config import Settings


def get_embeddings(settings: Settings) -> Embeddings:
    """Return the configured embedding model. HuggingFace runs locally (no API cost)."""
    if settings.EMBEDDING_BACKEND == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )

    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=settings.HF_EMBEDDING_MODEL)
