"""API tests for the reports module: listing, filtering, pagination, detail."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.auth_utils import access_token_from_cookie

PW = "S3curePass!"


async def _register(client: AsyncClient, email: str) -> tuple[str, int]:
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": PW})
    uid = r.json()["data"]["id"]
    await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return access_token_from_cookie(client), uid


@pytest.mark.asyncio
async def test_reports_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/reports")).status_code == 401
    assert (await client.get("/api/v1/reports/1")).status_code == 401
    assert (await client.get("/api/v1/reports/1/export")).status_code == 401


@pytest.mark.asyncio
async def test_list_detail_and_type_filter(client: AsyncClient, seed_reports) -> None:
    token, uid = await _register(client, "rep1@example.com")
    h = {"Authorization": f"Bearer {token}"}
    daily = await seed_reports(uid, "daily")
    weekly = await seed_reports(uid, "weekly")

    all_rows = (await client.get("/api/v1/reports", headers=h)).json()["data"]
    assert {r["id"] for r in all_rows} == {daily.id, weekly.id}

    only_weekly = (await client.get("/api/v1/reports?report_type=weekly", headers=h)).json()["data"]
    assert [r["id"] for r in only_weekly] == [weekly.id]

    detail = await client.get(f"/api/v1/reports/{daily.id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["data"]["sections"]["executive_summary"]


@pytest.mark.asyncio
async def test_pagination(client: AsyncClient, seed_reports) -> None:
    token, uid = await _register(client, "rep2@example.com")
    h = {"Authorization": f"Bearer {token}"}
    for _ in range(5):
        await seed_reports(uid, "daily")

    page1 = (await client.get("/api/v1/reports?limit=2&offset=0", headers=h)).json()["data"]
    page2 = (await client.get("/api/v1/reports?limit=2&offset=2", headers=h)).json()["data"]
    page3 = (await client.get("/api/v1/reports?limit=2&offset=4", headers=h)).json()["data"]
    assert len(page1) == 2 and len(page2) == 2 and len(page3) == 1
    ids = {r["id"] for r in page1 + page2 + page3}
    assert len(ids) == 5  # no overlap across pages


@pytest.mark.asyncio
async def test_date_filter(client: AsyncClient, seed_reports) -> None:
    token, uid = await _register(client, "rep3@example.com")
    h = {"Authorization": f"Bearer {token}"}
    await seed_reports(uid, "daily", created=datetime(2024, 1, 10, 12, tzinfo=timezone.utc))

    # A window before the report → nothing.
    empty = (await client.get("/api/v1/reports?end_date=2024-01-05", headers=h)).json()["data"]
    assert empty == []
    # A window covering it → present.
    hit = (await client.get("/api/v1/reports?start_date=2024-01-01&end_date=2024-01-31", headers=h)).json()["data"]
    assert len(hit) == 1


@pytest.mark.asyncio
async def test_report_ownership(client: AsyncClient, seed_reports) -> None:
    token_a, uid_a = await _register(client, "repa@example.com")
    token_b, _ = await _register(client, "repb@example.com")
    report = await seed_reports(uid_a, "daily")
    other = {"Authorization": f"Bearer {token_b}"}
    assert (await client.get(f"/api/v1/reports/{report.id}", headers=other)).status_code == 404
    assert (await client.get(f"/api/v1/reports/{report.id}/export", headers=other)).status_code == 404
