"""External constituent discovery for the database-backed market universe."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Protocol

import httpx

NIFTY50_INDEX_CODE = "NIFTY50"
NSE_NIFTY50_CSV_URL = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
)
NSE_INDEX_SOURCE = "nse-indices-csv"
EXPECTED_NIFTY50_COUNT = 50
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]*$")


class UniverseProviderError(RuntimeError):
    """The external source could not provide a trustworthy snapshot."""


class UniverseProviderUnavailableError(UniverseProviderError):
    """The external source was unreachable or returned an HTTP failure."""


class UniversePayloadError(UniverseProviderError):
    """The external response was reachable but malformed or incomplete."""


@dataclass(frozen=True)
class UniverseConstituent:
    index_code: str
    exchange_symbol: str
    company_name: str
    industry: str | None
    series: str | None
    isin: str | None
    weight: float | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "UniverseConstituent":
        return cls(
            index_code=str(payload["index_code"]),
            exchange_symbol=str(payload["exchange_symbol"]),
            company_name=str(payload["company_name"]),
            industry=_optional_string(payload.get("industry")),
            series=_optional_string(payload.get("series")),
            isin=_optional_string(payload.get("isin")),
            weight=float(payload["weight"])
            if payload.get("weight") is not None
            else None,
        )


@dataclass(frozen=True)
class UniverseProviderSnapshot:
    index_code: str
    source: str
    source_url: str | None
    snapshot_date: date
    fetched_at: datetime
    constituents: tuple[UniverseConstituent, ...]

    @property
    def checksum(self) -> str:
        serialized = json.dumps(
            [row.to_payload() for row in self.constituents],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(serialized).hexdigest()


class UniverseProvider(Protocol):
    source: str

    async def get_constituents(self, index_code: str) -> UniverseProviderSnapshot:
        """Return a normalized, shape-validated constituent snapshot."""


def parse_nifty50_csv(
    content: bytes,
    *,
    snapshot_date: date,
    fetched_at: datetime,
) -> UniverseProviderSnapshot:
    """Parse the official CSV defensively and require all 50 unique constituents."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UniversePayloadError("NSE constituent CSV is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {name.strip() for name in (reader.fieldnames or []) if name}
    required = {"Company Name", "Industry", "Symbol"}
    if not required.issubset(fieldnames):
        missing = ", ".join(sorted(required - fieldnames))
        raise UniversePayloadError(f"NSE constituent CSV is missing columns: {missing}")

    constituents: list[UniverseConstituent] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(reader, start=2):
        row = {(key or "").strip(): (value or "").strip() for key, value in raw.items()}
        symbol = row.get("Symbol", "").upper()
        name = row.get("Company Name", "")
        if not symbol or not name or not _SYMBOL_PATTERN.fullmatch(symbol):
            raise UniversePayloadError(
                f"NSE constituent CSV has an invalid row at line {line_number}"
            )
        if symbol in seen:
            raise UniversePayloadError(f"NSE constituent CSV duplicates {symbol}")
        seen.add(symbol)
        constituents.append(
            UniverseConstituent(
                index_code=NIFTY50_INDEX_CODE,
                exchange_symbol=symbol,
                company_name=name,
                industry=row.get("Industry") or None,
                series=row.get("Series") or None,
                isin=row.get("ISIN Code") or None,
            )
        )

    if len(constituents) != EXPECTED_NIFTY50_COUNT:
        raise UniversePayloadError(
            "NSE NIFTY 50 response must contain exactly "
            f"{EXPECTED_NIFTY50_COUNT} unique rows; received {len(constituents)}"
        )
    return UniverseProviderSnapshot(
        index_code=NIFTY50_INDEX_CODE,
        source=NSE_INDEX_SOURCE,
        source_url=NSE_NIFTY50_CSV_URL,
        snapshot_date=snapshot_date,
        fetched_at=fetched_at,
        constituents=tuple(sorted(constituents, key=lambda row: row.exchange_symbol)),
    )


class NseNifty50Provider:
    """Fetch the official machine-readable NSE Indices constituent CSV."""

    source = NSE_INDEX_SOURCE

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.client_factory = client_factory
        self.today = today

    async def get_constituents(self, index_code: str) -> UniverseProviderSnapshot:
        if index_code.upper() != NIFTY50_INDEX_CODE:
            raise UniverseProviderError(f"Unsupported universe index: {index_code}")
        fetched_at = datetime.now(tz=timezone.utc)
        try:
            async with self.client_factory(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                headers={
                    "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.5",
                    "User-Agent": "FinSight-AI-Universe/1.0",
                },
            ) as client:
                response = await client.get(NSE_NIFTY50_CSV_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UniverseProviderUnavailableError(
                f"Official NSE NIFTY 50 source unavailable: {type(exc).__name__}"
            ) from exc
        if not response.content:
            raise UniversePayloadError(
                "Official NSE NIFTY 50 source returned an empty body"
            )
        return parse_nifty50_csv(
            response.content,
            snapshot_date=self.today(),
            fetched_at=fetched_at,
        )


def _optional_string(value: object) -> str | None:
    return str(value) if value not in (None, "") else None
