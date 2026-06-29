import os
from datetime import datetime, timezone

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import DocumentRow
from app.vector_store import FAISSVectorStore, VectorStore

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md"}


def load_documents(path: str) -> list[Document]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return PyPDFLoader(path).load()
    if ext == ".docx":
        return Docx2txtLoader(path).load()
    if ext in {".txt", ".md"}:
        return TextLoader(path).load()
    raise ValueError(f"Unsupported file type: {ext}")


def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    return splitter.split_documents(docs)


async def run_ingest(tenant_id: str, vector_store: FAISSVectorStore, db: AsyncSession) -> None:
    """Phase 1 — Full rebuild: loads all docs for tenant, rebuilds FAISS index."""
    docs_dir = os.path.join(settings.INPUT_DOCS_PATH, tenant_id)
    if not os.path.exists(docs_dir):
        return

    all_chunks: list[Document] = []
    chunk_counts: dict[str, int] = {}

    for filename in os.listdir(docs_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        path = os.path.join(docs_dir, filename)
        try:
            docs = load_documents(path)
            chunks = chunk_documents(docs)
            for chunk in chunks:
                chunk.metadata.setdefault("source", filename)
                chunk.metadata.setdefault("tenant_id", tenant_id)
            all_chunks.extend(chunks)
            chunk_counts[filename] = len(chunks)
        except Exception:
            pass

    vector_store.rebuild(tenant_id, all_chunks)

    for filename, count in chunk_counts.items():
        await db.execute(
            update(DocumentRow)
            .where(DocumentRow.tenant_id == tenant_id, DocumentRow.filename == filename)
            .values(chunk_count=count)
        )
    await db.commit()


async def add_or_update_document(
    tenant_id: str,
    filename: str,
    vector_store: VectorStore,
    db: AsyncSession,
) -> None:
    """Phase 2 — Per-doc upsert for pgvector/Pinecone/Qdrant."""
    path = os.path.join(settings.INPUT_DOCS_PATH, tenant_id, filename)
    docs = load_documents(path)
    chunks = chunk_documents(docs)
    for chunk in chunks:
        chunk.metadata.setdefault("source", filename)
        chunk.metadata.setdefault("tenant_id", tenant_id)

    count = vector_store.update_documents(tenant_id, filename, chunks)

    await db.execute(
        update(DocumentRow)
        .where(DocumentRow.tenant_id == tenant_id, DocumentRow.filename == filename)
        .values(chunk_count=count, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def delete_document(
    tenant_id: str,
    filename: str,
    vector_store: VectorStore,
    db: AsyncSession,
) -> None:
    # FAISS doesn't support per-doc delete — skip it; the caller queues _trigger_rebuild
    # after this task, which rebuilds from whatever files remain on disk.
    if not isinstance(vector_store, FAISSVectorStore):
        vector_store.delete_documents(tenant_id, filename)
    result = await db.execute(
        select(DocumentRow).where(
            DocumentRow.tenant_id == tenant_id,
            DocumentRow.filename == filename,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()

    # Remove file from disk
    path = os.path.join(settings.INPUT_DOCS_PATH, tenant_id, filename)
    if os.path.exists(path):
        os.remove(path)
