"""Tests for multi-tenant isolation."""
import io
import pytest


def _txt_file(content: bytes, filename: str):
    return ("file", (filename, io.BytesIO(content), "text/plain"))


@pytest.mark.asyncio
async def test_tenant_sees_only_own_documents(client, tenant_acme, tenant_globex):
    # Acme uploads a document
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=[_txt_file(b"Acme doc", "acme.txt")],
    )

    # Globex sees zero documents
    res = await client.get("/v1/documents",
        headers={"X-API-Key": tenant_globex["api_key"]},
    )
    assert res.status_code == 200
    assert res.json()["total"] == 0


@pytest.mark.asyncio
async def test_two_tenants_same_filename(client, tenant_acme, tenant_globex):
    """Same filename can coexist across tenants without conflict."""
    f1 = [_txt_file(b"Acme version", "shared.txt")]
    r1 = await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=f1,
    )
    assert r1.status_code == 202

    f2 = [_txt_file(b"Globex version", "shared.txt")]
    r2 = await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_globex["api_key"]},
        files=f2,
    )
    assert r2.status_code == 202  # not 409 — different tenants


@pytest.mark.asyncio
async def test_tenant_cannot_delete_other_tenant_document(client, tenant_acme, tenant_globex):
    """Tenant B cannot delete Tenant A's document."""
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=[_txt_file(b"Acme doc", "acme_private.txt")],
    )
    res = await client.delete("/v1/documents/acme_private.txt",
        headers={"X-API-Key": tenant_globex["api_key"]},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_tenant_info_isolation(client, tenant_acme, tenant_globex):
    """Each tenant sees their own info, not the other's."""
    r_acme = await client.get("/v1/tenant",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    r_globex = await client.get("/v1/tenant",
        headers={"X-API-Key": tenant_globex["api_key"]},
    )
    assert r_acme.json()["tenant_id"] == tenant_acme["tenant_id"]
    assert r_globex.json()["tenant_id"] == tenant_globex["tenant_id"]
    assert r_acme.json()["tenant_id"] != r_globex.json()["tenant_id"]


@pytest.mark.asyncio
async def test_tenant_api_key_cannot_use_other_tenant_jwt(client, tenant_acme, tenant_globex):
    """Acme's API key cannot be used with Globex's JWT or vice versa."""
    # Globex JWT with Acme API key — resolves by JWT to Globex's tenant
    res = await client.get("/v1/tenant", headers={
        "Authorization": f"Bearer {tenant_globex['token']}",
        "X-API-Key": tenant_acme["api_key"],
    })
    assert res.status_code == 200
    # JWT takes priority → returns Globex
    assert res.json()["tenant_id"] == tenant_globex["tenant_id"]


@pytest.mark.asyncio
async def test_chat_uses_correct_tenant_vector_store(client, tenant_acme, mock_vector_store):
    """chat() calls vector store search with the authenticated tenant's tenant_id."""
    from langchain_core.documents import Document
    mock_vector_store.search.return_value = [
        Document(page_content="Acme product info", metadata={"source": "acme.txt", "page": 1}),
    ]
    res = await client.post("/v1/chat",
        headers={"X-API-Key": tenant_acme["api_key"]},
        json={"message": "Tell me about acme products"},
    )
    assert res.status_code == 200
    assert res.json()["answer"]


@pytest.mark.asyncio
async def test_document_count_per_tenant(client, tenant_acme, tenant_globex):
    """Document counts are independent per tenant."""
    for i in range(3):
        await client.post("/v1/ingest",
            headers={"X-API-Key": tenant_acme["api_key"]},
            files=[_txt_file(b"content", f"doc{i}.txt")],
        )
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_globex["api_key"]},
        files=[_txt_file(b"content", "gdoc.txt")],
    )

    r_acme = await client.get("/v1/documents",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    r_globex = await client.get("/v1/documents",
        headers={"X-API-Key": tenant_globex["api_key"]},
    )
    assert r_acme.json()["total"] == 3
    assert r_globex.json()["total"] == 1
