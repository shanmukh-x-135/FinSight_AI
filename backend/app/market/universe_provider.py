"""External constituent discovery for the database-backed market universe."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Protocol

import httpx

from app.shared.time import utc_now

NIFTY50_INDEX_CODE = "NIFTY50"
NIFTY_NEXT50_INDEX_CODE = "NIFTYNEXT50"
NIFTY100_INDEX_CODE = "NIFTY100"
SUPPORTED_INDEX_CODES = (
    NIFTY50_INDEX_CODE,
    NIFTY_NEXT50_INDEX_CODE,
    NIFTY100_INDEX_CODE,
)
NSE_INDEX_SOURCE = "nse-indices-csv"
EXPECTED_NIFTY50_COUNT = 50
EXPECTED_NIFTY_NEXT50_COUNT = 50
EXPECTED_NIFTY100_COUNT = 100
NSE_NIFTY50_CSV_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"
)
NSE_NIFTY_NEXT50_CSV_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_niftynext50list.csv"
)
NSE_NIFTY100_CSV_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
)
INDEX_DEFINITIONS: dict[str, tuple[str, str, int]] = {
    NIFTY50_INDEX_CODE: ("NIFTY 50", NSE_NIFTY50_CSV_URL, EXPECTED_NIFTY50_COUNT),
    NIFTY_NEXT50_INDEX_CODE: (
        "NIFTY Next 50",
        NSE_NIFTY_NEXT50_CSV_URL,
        EXPECTED_NIFTY_NEXT50_COUNT,
    ),
    NIFTY100_INDEX_CODE: ("NIFTY 100", NSE_NIFTY100_CSV_URL, EXPECTED_NIFTY100_COUNT),
}
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


def parse_index_csv(
    content: bytes,
    *,
    index_code: str,
    snapshot_date: date,
    fetched_at: datetime,
) -> UniverseProviderSnapshot:
    """Parse one official index CSV and require its exact constituent count."""
    normalized_code = index_code.strip().upper()
    definition = INDEX_DEFINITIONS.get(normalized_code)
    if definition is None:
        raise UniverseProviderError(f"Unsupported universe index: {index_code}")
    display_name, source_url, expected_count = definition
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
                index_code=normalized_code,
                exchange_symbol=symbol,
                company_name=name,
                industry=row.get("Industry") or None,
                series=row.get("Series") or None,
                isin=row.get("ISIN Code") or None,
            )
        )

    if len(constituents) != expected_count:
        raise UniversePayloadError(
            f"NSE {display_name} response must contain exactly "
            f"{expected_count} unique rows; received {len(constituents)}"
        )
    return UniverseProviderSnapshot(
        index_code=normalized_code,
        source=NSE_INDEX_SOURCE,
        source_url=source_url,
        snapshot_date=snapshot_date,
        fetched_at=fetched_at,
        constituents=tuple(sorted(constituents, key=lambda row: row.exchange_symbol)),
    )


def parse_nifty50_csv(
    content: bytes,
    *,
    snapshot_date: date,
    fetched_at: datetime,
) -> UniverseProviderSnapshot:
    """Backward-compatible NIFTY 50 parser wrapper."""
    return parse_index_csv(
        content,
        index_code=NIFTY50_INDEX_CODE,
        snapshot_date=snapshot_date,
        fetched_at=fetched_at,
    )


class NseIndexConstituentProvider:
    """Fetch official machine-readable Nifty Indices constituent CSVs."""

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
        normalized_code = index_code.strip().upper()
        definition = INDEX_DEFINITIONS.get(normalized_code)
        if definition is None:
            raise UniverseProviderError(f"Unsupported universe index: {index_code}")
        display_name, source_url, _expected_count = definition
        fetched_at = utc_now()
        try:
            async with self.client_factory(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                headers={
                    "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.5",
                    "User-Agent": "FinSight-AI-Universe/1.0",
                },
            ) as client:
                response = await client.get(source_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UniverseProviderUnavailableError(
                f"Official NSE {display_name} source unavailable: {type(exc).__name__}"
            ) from exc
        if not response.content:
            raise UniversePayloadError(
                f"Official NSE {display_name} source returned an empty body"
            )
        return parse_index_csv(
            response.content,
            index_code=normalized_code,
            snapshot_date=self.today(),
            fetched_at=fetched_at,
        )


# Compatibility alias retained for callers and operators introduced in Phase 10.
NseNifty50Provider = NseIndexConstituentProvider


def _optional_string(value: object) -> str | None:
    return str(value) if value not in (None, "") else None
