"""Tests for document ingest, list, replace, and delete endpoints."""
import io
import pytest


def _txt_file(content: bytes, filename: str):
    return ("file", (filename, io.BytesIO(content), "text/plain"))


@pytest.mark.asyncio
async def test_ingest_txt_success(client, tenant_acme, tmp_path):
    files = [_txt_file(b"Hello world document content.", "doc.txt")]
    res = await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "accepted"
    assert data["filename"] == "doc.txt"


@pytest.mark.asyncio
async def test_ingest_md_success(client, tenant_acme):
    files = [_txt_file(b"# Markdown doc\nSome content.", "readme.md")]
    res = await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    assert res.status_code == 202


@pytest.mark.asyncio
async def test_ingest_unsupported_type(client, tenant_acme):
    files = [_txt_file(b"binary", "program.exe")]
    res = await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_ingest_duplicate_filename(client, tenant_acme):
    files = [_txt_file(b"content", "dup.txt")]
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    files2 = [_txt_file(b"content", "dup.txt")]
    res = await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files2,
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_ingest_requires_auth(client):
    files = [_txt_file(b"content", "test.txt")]
    res = await client.post("/v1/ingest", files=files)
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_documents_empty(client, tenant_acme):
    res = await client.get("/v1/documents",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["documents"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_documents_after_upload(client, tenant_acme):
    files = [_txt_file(b"content here", "listed.txt")]
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    res = await client.get("/v1/documents",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["documents"][0]["filename"] == "listed.txt"


@pytest.mark.asyncio
async def test_replace_document(client, tenant_acme):
    files = [_txt_file(b"v1 content", "replace.txt")]
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    files2 = [_txt_file(b"v2 content", "replace.txt")]
    res = await client.put("/v1/documents/replace.txt",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files2,
    )
    assert res.status_code == 202
    assert res.json()["filename"] == "replace.txt"


@pytest.mark.asyncio
async def test_replace_nonexistent_document(client, tenant_acme):
    files = [_txt_file(b"content", "ghost.txt")]
    res = await client.put("/v1/documents/ghost.txt",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_document(client, tenant_acme):
    files = [_txt_file(b"delete me", "todelete.txt")]
    await client.post("/v1/ingest",
        headers={"X-API-Key": tenant_acme["api_key"]},
        files=files,
    )
    res = await client.delete("/v1/documents/todelete.txt",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    assert res.status_code == 202


@pytest.mark.asyncio
async def test_delete_nonexistent_document(client, tenant_acme):
    res = await client.delete("/v1/documents/missing.txt",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    assert res.status_code == 404
