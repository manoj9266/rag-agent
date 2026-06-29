"""Tests for auth endpoints and auth dependency."""
import pytest


@pytest.mark.asyncio
async def test_register_success(client):
    res = await client.post("/v1/auth/register", json={
        "company_name": "TestCo",
        "email": "test@testco.com",
        "password": "securepass123",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["tenant_id"].startswith("testco-")
    assert data["api_key"].startswith("sk-")
    assert "access_token" in data
    assert data["name"] == "TestCo"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"company_name": "Dup Co", "email": "dup@test.com", "password": "password123"}
    await client.post("/v1/auth/register", json=payload)
    res = await client.post("/v1/auth/register", json=payload)
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_register_password_too_short(client):
    res = await client.post("/v1/auth/register", json={
        "company_name": "Co",
        "email": "short@test.com",
        "password": "abc",
    })
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/v1/auth/register", json={
        "company_name": "LoginCo",
        "email": "login@loginco.com",
        "password": "password123",
    })
    res = await client.post("/v1/auth/login", json={
        "email": "login@loginco.com",
        "password": "password123",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["api_key"].startswith("sk-")


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/v1/auth/register", json={
        "company_name": "WrongPass",
        "email": "wrong@test.com",
        "password": "correctpass",
    })
    res = await client.post("/v1/auth/login", json={
        "email": "wrong@test.com",
        "password": "wrongpassword",
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    res = await client.post("/v1/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "anypassword",
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_tenant_via_jwt(client, tenant_acme):
    res = await client.get("/v1/tenant", headers={
        "Authorization": f"Bearer {tenant_acme['token']}",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == tenant_acme["tenant_id"]
    assert data["name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_get_tenant_via_api_key(client, tenant_acme):
    res = await client.get("/v1/tenant", headers={
        "X-API-Key": tenant_acme["api_key"],
    })
    assert res.status_code == 200
    assert res.json()["tenant_id"] == tenant_acme["tenant_id"]


@pytest.mark.asyncio
async def test_get_tenant_no_auth(client):
    res = await client.get("/v1/tenant")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_tenant_invalid_api_key(client):
    res = await client.get("/v1/tenant", headers={"X-API-Key": "sk-invalid"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_valid_key(client):
    res = await client.get("/admin/tenants", headers={"X-Admin-Key": "test-admin-key"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_admin_invalid_key(client):
    res = await client.get("/admin/tenants", headers={"X-Admin-Key": "wrong-key"})
    assert res.status_code == 403
