"""Tests for health, chat, and session endpoints."""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["index_ready"] is True
    assert isinstance(data["doc_count"], int)
    assert isinstance(data["uptime_seconds"], float)


@pytest.mark.asyncio
async def test_chat_returns_mocked_answer(client, tenant_acme):
    res = await client.post("/v1/chat",
        headers={"X-API-Key": tenant_acme["api_key"]},
        json={"message": "What is the product?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "session_id" in data
    assert isinstance(data["sources"], list)
    assert isinstance(data["tools_used"], list)


@pytest.mark.asyncio
async def test_chat_session_id_preserved(client, tenant_acme):
    res = await client.post("/v1/chat",
        headers={"X-API-Key": tenant_acme["api_key"]},
        json={"message": "Hello", "session_id": "my-session-123"},
    )
    assert res.status_code == 200
    assert res.json()["session_id"] == "my-session-123"


@pytest.mark.asyncio
async def test_chat_generates_session_id_if_missing(client, tenant_acme):
    res = await client.post("/v1/chat",
        headers={"X-API-Key": tenant_acme["api_key"]},
        json={"message": "Hello"},
    )
    assert res.status_code == 200
    assert res.json()["session_id"]  # non-empty


@pytest.mark.asyncio
async def test_chat_requires_auth(client):
    res = await client.post("/v1/chat", json={"message": "Hello"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_delete_session(client, tenant_acme):
    res = await client.delete("/v1/session/test-session",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_delete_session_requires_auth(client):
    res = await client.delete("/v1/session/test-session")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_tenants(client, tenant_acme, tenant_globex):
    res = await client.get("/admin/tenants",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert res.status_code == 200
    tenants = res.json()
    ids = [t["tenant_id"] for t in tenants]
    assert tenant_acme["tenant_id"] in ids
    assert tenant_globex["tenant_id"] in ids


@pytest.mark.asyncio
async def test_admin_rotate_key(client, tenant_acme):
    res = await client.post(f"/admin/tenants/{tenant_acme['tenant_id']}/rotate-key",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["api_key"] != tenant_acme["api_key"]
    assert data["api_key"].startswith("sk-")


@pytest.mark.asyncio
async def test_admin_delete_tenant(client, tenant_acme):
    res = await client.delete(f"/admin/tenants/{tenant_acme['tenant_id']}",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert res.status_code == 204

    # Tenant's API key should now be invalid
    res2 = await client.get("/v1/tenant",
        headers={"X-API-Key": tenant_acme["api_key"]},
    )
    assert res2.status_code == 401
