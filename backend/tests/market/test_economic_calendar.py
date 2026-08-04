from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.shared.clients.economic_calendar import TradingEconomicsCalendarClient


@pytest.mark.asyncio
async def test_trading_economics_client_parses_and_sorts_valid_events() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "secret"
        assert request.url.path.endswith("/india/2026-08-04/2026-08-18")
        return httpx.Response(
            200,
            json=[
                {
                    "CalendarId": "2", "Date": "2026-08-08T06:30:00Z",
                    "Event": "CPI", "Importance": 3,
                },
                {"broken": True},
                {
                    "CalendarId": "1", "Date": "2026-08-06T06:30:00Z",
                    "Event": "PMI", "Importance": 2,
                },
            ],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.tradingeconomics.com",
    ) as http_client:
        client = TradingEconomicsCalendarClient("secret", client=http_client)
        events = await client.fetch_events(date(2026, 8, 4), date(2026, 8, 18))

    assert [event.event_id for event in events] == ["1", "2"]
    assert events[1].importance == 3
