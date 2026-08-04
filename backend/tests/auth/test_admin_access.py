"""Authorization boundary for operations-only job endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/jobs/market-ingestion/run",
        "/api/v1/admin/jobs/news-ingestion/run",
        "/api/v1/admin/jobs/history-rebuild/run",
    ],
)
async def test_authenticated_non_admin_cannot_run_jobs(
    client: AsyncClient, path: str
) -> None:
    password = "S3curePass!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": password},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": password},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    response = await client.post(path, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["type"] == "admin_access_required"
