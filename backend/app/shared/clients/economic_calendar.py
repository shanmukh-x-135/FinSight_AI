"""Economic-calendar provider abstraction and Trading Economics adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class EconomicEventData:
    event_id: str
    date: datetime
    country: str
    category: str
    name: str
    importance: int
    reference: str | None = None
    source: str | None = None
    source_url: str | None = None
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None


class EconomicCalendarClient(Protocol):
    async def fetch_events(
        self, start_date: date, end_date: date
    ) -> list[EconomicEventData]: ...


class TradingEconomicsCalendarClient:
    """Async adapter for Trading Economics' country/date calendar endpoint."""

    base_url = "https://api.tradingeconomics.com"

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.client = client

    async def fetch_events(
        self, start_date: date, end_date: date
    ) -> list[EconomicEventData]:
        path = f"/calendar/country/india/{start_date.isoformat()}/{end_date.isoformat()}"
        if self.client is not None:
            response = await self.client.get(
                path,
                headers={"Authorization": self.api_key},
                timeout=self.timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(base_url=self.base_url) as client:
                response = await client.get(
                    path,
                    headers={"Authorization": self.api_key},
                    timeout=self.timeout_seconds,
                )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Economic calendar provider returned a non-list payload")
        events = [event for row in payload if (event := self._parse_event(row))]
        return sorted(events, key=lambda event: event.date)

    @staticmethod
    def _parse_event(row: object) -> EconomicEventData | None:
        if not isinstance(row, dict):
            return None
        try:
            event_date = datetime.fromisoformat(str(row["Date"]).replace("Z", "+00:00"))
            if event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=timezone.utc)
            raw_source_url = str(row["SourceURL"]) if row.get("SourceURL") else None
            source_url = None
            if raw_source_url and urlparse(raw_source_url).scheme in {"http", "https"}:
                source_url = raw_source_url
            return EconomicEventData(
                event_id=str(row["CalendarId"]),
                date=event_date,
                country=str(row.get("Country") or "India"),
                category=str(row.get("Category") or "Economic event"),
                name=str(row["Event"]),
                importance=max(1, min(3, int(row.get("Importance") or 1))),
                reference=str(row["Reference"]) if row.get("Reference") else None,
                source=str(row["Source"]) if row.get("Source") else None,
                source_url=source_url,
                actual=str(row["Actual"]) if row.get("Actual") else None,
                forecast=str(row["Forecast"]) if row.get("Forecast") else None,
                previous=str(row["Previous"]) if row.get("Previous") else None,
            )
        except (KeyError, TypeError, ValueError):
            return None
