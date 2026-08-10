"""API tests for the intelligence routes (reports + recommendations)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.intelligence.models import Report

PW = "S3curePass!"


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PW})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_generate_requires_auth(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/reports/generate")).status_code == 401
    assert (await client.get("/api/v1/recommendations")).status_code == 401


@pytest.mark.asyncio
async def test_generate_list_get_report(client: AsyncClient, seed_market) -> None:
    headers = {"Authorization": f"Bearer {await _token(client, 'r6@example.com')}"}

    gen = await client.post("/api/v1/reports/generate", headers=headers)
    assert gen.status_code == 201
    report = gen.json()["data"]
    assert report["sections"]["market_summary"]["narrative"]
    assert report["sections"]["executive_summary"]
    assert report["sections"]["meta"]["generation"]["schema_version"] == 1
    rid = report["id"]

    listed = await client.get("/api/v1/reports", headers=headers)
    assert rid in [r["id"] for r in listed.json()["data"]]

    got = await client.get(f"/api/v1/reports/{rid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["data"]["id"] == rid


@pytest.mark.asyncio
async def test_generate_reuses_report_for_the_same_idempotency_key(
    client: AsyncClient, db_session, seed_market
) -> None:
    headers = {
        "Authorization": f"Bearer {await _token(client, 'retry6@example.com')}",
        "Idempotency-Key": "report-request-123",
    }

    first = await client.post("/api/v1/reports/generate", headers=headers)
    second = await client.post("/api/v1/reports/generate", headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert await db_session.scalar(select(func.count()).select_from(Report)) == 1
    stored = await db_session.scalar(select(Report))
    assert stored.idempotency_key_hash != "report-request-123"


@pytest.mark.asyncio
async def test_report_idempotency_key_is_scoped_per_user(
    client: AsyncClient, seed_market
) -> None:
    key = "same-client-key"
    first_headers = {
        "Authorization": f"Bearer {await _token(client, 'scope-a@example.com')}",
        "Idempotency-Key": key,
    }
    second_headers = {
        "Authorization": f"Bearer {await _token(client, 'scope-b@example.com')}",
        "Idempotency-Key": key,
    }

    first = await client.post("/api/v1/reports/generate", headers=first_headers)
    second = await client.post("/api/v1/reports/generate", headers=second_headers)

    assert first.json()["data"]["id"] != second.json()["data"]["id"]


@pytest.mark.asyncio
async def test_report_ownership_via_api(client: AsyncClient, seed_market) -> None:
    a = {"Authorization": f"Bearer {await _token(client, 'a6@example.com')}"}
    b = {"Authorization": f"Bearer {await _token(client, 'b6@example.com')}"}
    rid = (await client.post("/api/v1/reports/generate", headers=a)).json()["data"]["id"]
    assert (await client.get(f"/api/v1/reports/{rid}", headers=b)).status_code == 404


@pytest.mark.asyncio
async def test_recommendations_endpoint(client: AsyncClient, seed_market) -> None:
    headers = {"Authorization": f"Bearer {await _token(client, 'rec6@example.com')}"}
    resp = await client.get("/api/v1/recommendations", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "AAA.NS" in {r["symbol"] for r in data["watchlist"]}
    assert all(r["evidence"] and r["explanation"] for r in data["watchlist"])
    assert data["generation"]["actual_backends"] == ["deterministic"]
