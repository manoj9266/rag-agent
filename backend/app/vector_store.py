import os
from typing import Protocol, runtime_checkable

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import Settings


@runtime_checkable
class VectorStore(Protocol):
    def add_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int: ...
    def update_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int: ...
    def delete_documents(self, tenant_id: str, filename: str) -> None: ...
    def search(self, tenant_id: str, query: str, top_k: int) -> list[Document]: ...
    def is_ready(self, tenant_id: str) -> bool: ...


class FAISSVectorStore:
    """Phase 1: per-tenant FAISS indexes on disk. Rebuild on every change."""

    def __init__(self, settings: Settings) -> None:
        self._base_path = settings.FAISS_INDEX_PATH
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )
        self._indexes: dict[str, FAISS] = {}

    def _index_path(self, tenant_id: str) -> str:
        return os.path.join(self._base_path, tenant_id)

    def _load(self, tenant_id: str) -> FAISS | None:
        if tenant_id in self._indexes:
            return self._indexes[tenant_id]
        path = self._index_path(tenant_id)
        if os.path.exists(path):
            index = FAISS.load_local(path, self._embeddings, allow_dangerous_deserialization=True)
            self._indexes[tenant_id] = index
            return index
        return None 

    def _save(self, tenant_id: str, index: FAISS) -> None:
        path = self._index_path(tenant_id)
        os.makedirs(path, exist_ok=True)
        index.save_local(path)
        self._indexes[tenant_id] = index

    def rebuild(self, tenant_id: str, all_chunks: list[Document]) -> None:
        """Replace the entire index for a tenant. Called by ingest.run_ingest()."""
        if not all_chunks:
            return
        index = FAISS.from_documents(all_chunks, self._embeddings)
        self._save(tenant_id, index)

    def add_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        # FAISS doesn't support incremental add per-file without a full rebuild;
        # callers are expected to use rebuild() in Phase 1.
        raise NotImplementedError("Use rebuild() for FAISSVectorStore")

    def update_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        raise NotImplementedError("Use rebuild() for FAISSVectorStore")

    def delete_documents(self, tenant_id: str, filename: str) -> None:
        raise NotImplementedError("Use rebuild() for FAISSVectorStore")

    def search(self, tenant_id: str, query: str, top_k: int) -> list[Document]:
        index = self._load(tenant_id)
        if index is None:
            return []
        return index.similarity_search(query, k=top_k)

    def is_ready(self, tenant_id: str) -> bool:
        return self._load(tenant_id) is not None


class PGVectorStore:
    """Phase 2A: per-document ops via pgvector (chunks table)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )

    def add_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        from langchain_community.vectorstores import PGVector
        store = PGVector(
            connection_string=self._settings.DATABASE_URL.replace("+asyncpg", ""),
            embedding_function=self._embeddings,
            collection_name=tenant_id,
        )
        for chunk in chunks:
            chunk.metadata.setdefault("tenant_id", tenant_id)
            chunk.metadata.setdefault("filename", filename)
        store.add_documents(chunks)
        return len(chunks)

    def update_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        self.delete_documents(tenant_id, filename)
        return self.add_documents(tenant_id, filename, chunks)

    def delete_documents(self, tenant_id: str, filename: str) -> None:
        # Direct SQL delete by (tenant_id, filename) — pgvector stores metadata in JSONB
        import psycopg2
        sync_url = self._settings.DATABASE_URL.replace("+asyncpg", "")
        conn = psycopg2.connect(sync_url)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'tenant_id'=%s AND cmetadata->>'filename'=%s",
                (tenant_id, filename),
            )
        conn.commit()
        conn.close()

    def search(self, tenant_id: str, query: str, top_k: int) -> list[Document]:
        from langchain_community.vectorstores import PGVector
        store = PGVector(
            connection_string=self._settings.DATABASE_URL.replace("+asyncpg", ""),
            embedding_function=self._embeddings,
            collection_name=tenant_id,
        )
        return store.similarity_search(query, k=top_k, filter={"tenant_id": tenant_id})

    def is_ready(self, tenant_id: str) -> bool:
        return True


class PineconeVectorStore:
    """Phase 2B: Pinecone managed cloud, namespace per tenant."""

    def __init__(self, settings: Settings) -> None:
        from pinecone import Pinecone  # type: ignore
        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self._index = self._pc.Index(settings.PINECONE_INDEX_NAME)
        self._settings = settings
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )

    def _embed(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)

    def add_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        vectors = [
            (f"{tenant_id}:{filename}:{i}", self._embed(c.page_content), {**c.metadata, "text": c.page_content})
            for i, c in enumerate(chunks)
        ]
        self._index.upsert(vectors=vectors, namespace=tenant_id)
        return len(chunks)

    def update_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        self.delete_documents(tenant_id, filename)
        return self.add_documents(tenant_id, filename, chunks)

    def delete_documents(self, tenant_id: str, filename: str) -> None:
        self._index.delete(filter={"filename": filename}, namespace=tenant_id)

    def search(self, tenant_id: str, query: str, top_k: int) -> list[Document]:
        vec = self._embed(query)
        results = self._index.query(vector=vec, top_k=top_k, namespace=tenant_id, include_metadata=True)
        return [
            Document(page_content=m["metadata"].get("text", ""), metadata=m["metadata"])
            for m in results.get("matches", [])
        ]

    def is_ready(self, tenant_id: str) -> bool:
        return True


class QdrantVectorStore:
    """Phase 2C: Qdrant self-hosted, one collection filtered by tenant_id."""

    def __init__(self, settings: Settings) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        self._client = QdrantClient(url=settings.QDRANT_URL)
        self._collection = settings.QDRANT_COLLECTION
        self._settings = settings
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )

    def _embed(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)

    def add_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        from qdrant_client.models import PointStruct  # type: ignore
        points = [
            PointStruct(
                id=abs(hash(f"{tenant_id}:{filename}:{i}")) % (2**63),
                vector=self._embed(c.page_content),
                payload={"tenant_id": tenant_id, "filename": filename, "text": c.page_content, **c.metadata},
            )
            for i, c in enumerate(chunks)
        ]
        self._client.upsert(collection_name=self._collection, points=points)
        return len(chunks)

    def update_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int:
        self.delete_documents(tenant_id, filename)
        return self.add_documents(tenant_id, filename, chunks)

    def delete_documents(self, tenant_id: str, filename: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                    FieldCondition(key="filename", match=MatchValue(value=filename)),
                ]
            ),
        )

    def search(self, tenant_id: str, query: str, top_k: int) -> list[Document]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore
        results = self._client.search(
            collection_name=self._collection,
            query_vector=self._embed(query),
            query_filter=Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]),
            limit=top_k,
        )
        return [Document(page_content=r.payload.get("text", ""), metadata=r.payload) for r in results]

    def is_ready(self, tenant_id: str) -> bool:
        return True


def get_vector_store(settings: Settings) -> VectorStore:
    match settings.VECTOR_BACKEND:
        case "pgvector":
            return PGVectorStore(settings)
        case "pinecone":
            return PineconeVectorStore(settings)
        case "qdrant":
            return QdrantVectorStore(settings)
        case _:
            return FAISSVectorStore(settings)
