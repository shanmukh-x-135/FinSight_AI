"""Official NIFTY 50 provider parsing and transport failure coverage."""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from app.market.universe_provider import (
    EXPECTED_NIFTY50_COUNT,
    EXPECTED_NIFTY100_COUNT,
    EXPECTED_NIFTY_NEXT50_COUNT,
    NIFTY50_INDEX_CODE,
    NIFTY100_INDEX_CODE,
    NIFTY_NEXT50_INDEX_CODE,
    NseIndexConstituentProvider,
    NseNifty50Provider,
    UniversePayloadError,
    UniverseProviderError,
    UniverseProviderUnavailableError,
    parse_index_csv,
    parse_nifty50_csv,
)

TARGET = date(2026, 8, 21)
FETCHED_AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def _csv(count: int = EXPECTED_NIFTY50_COUNT) -> bytes:
    rows = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    rows.extend(
        f"Company {index},Sector {index % 5},SYM{index:02d},EQ,INE{index:09d}"
        for index in range(count)
    )
    return ("\n".join(rows) + "\n").encode()


def test_parse_official_csv_normalizes_all_fifty_constituents() -> None:
    snapshot = parse_nifty50_csv(_csv(), snapshot_date=TARGET, fetched_at=FETCHED_AT)

    assert snapshot.index_code == NIFTY50_INDEX_CODE
    assert len(snapshot.constituents) == 50
    assert snapshot.constituents[0].exchange_symbol == "SYM00"
    assert snapshot.constituents[-1].isin == "INE000000049"
    assert len(snapshot.checksum) == 64


@pytest.mark.parametrize(
    ("index_code", "count"),
    [
        (NIFTY50_INDEX_CODE, EXPECTED_NIFTY50_COUNT),
        (NIFTY_NEXT50_INDEX_CODE, EXPECTED_NIFTY_NEXT50_COUNT),
        (NIFTY100_INDEX_CODE, EXPECTED_NIFTY100_COUNT),
    ],
)
def test_parse_all_supported_index_payloads(index_code: str, count: int) -> None:
    snapshot = parse_index_csv(
        _csv(count),
        index_code=index_code,
        snapshot_date=TARGET,
        fetched_at=FETCHED_AT,
    )

    assert snapshot.index_code == index_code
    assert len(snapshot.constituents) == count
    assert {row.index_code for row in snapshot.constituents} == {index_code}


@pytest.mark.parametrize(
    "payload",
    [
        b"Symbol,Industry\nABC,Energy\n",
        _csv(49),
        _csv().replace(b"SYM20", b"SYM19"),
        _csv().replace(b"SYM20", b"BAD SYMBOL"),
    ],
)
def test_parse_official_csv_rejects_malformed_or_incomplete_payload(
    payload: bytes,
) -> None:
    with pytest.raises(UniversePayloadError):
        parse_nifty50_csv(payload, snapshot_date=TARGET, fetched_at=FETCHED_AT)


@pytest.mark.asyncio
async def test_provider_classifies_unavailable_source() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    transport = httpx.MockTransport(fail)

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, **kwargs)

    provider = NseNifty50Provider(client_factory=client_factory)
    with pytest.raises(UniverseProviderUnavailableError):
        await provider.get_constituents(NIFTY50_INDEX_CODE)


@pytest.mark.asyncio
async def test_provider_fetches_and_parses_successful_response() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=_csv()))

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, **kwargs)

    provider = NseNifty50Provider(client_factory=client_factory, today=lambda: TARGET)
    snapshot = await provider.get_constituents(NIFTY50_INDEX_CODE)

    assert snapshot.snapshot_date == TARGET
    assert len(snapshot.constituents) == 50


@pytest.mark.asyncio
async def test_provider_selects_the_requested_official_index_source() -> None:
    requested_paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, content=_csv(EXPECTED_NIFTY100_COUNT))

    transport = httpx.MockTransport(respond)

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, **kwargs)

    snapshot = await NseIndexConstituentProvider(
        client_factory=client_factory, today=lambda: TARGET
    ).get_constituents(NIFTY100_INDEX_CODE)

    assert requested_paths == ["/IndexConstituent/ind_nifty100list.csv"]
    assert snapshot.index_code == NIFTY100_INDEX_CODE
    assert len(snapshot.constituents) == 100


@pytest.mark.asyncio
async def test_provider_rejects_an_unknown_index_before_transport() -> None:
    with pytest.raises(UniverseProviderError, match="Unsupported universe index"):
        await NseIndexConstituentProvider().get_constituents("NIFTY500")
