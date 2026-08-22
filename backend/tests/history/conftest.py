"""Shared fixtures for history tests: a controlled two-regime market + tmp
FAISS directory."""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.constants import MACRO_PROXIES
from app.market.models import DailyPrice, Indicator, Stock
from config.settings import settings

A_DATES = [date(2024, 1, d) for d in range(1, 11)]   # calm-up regime
B_DATES = [date(2024, 2, d) for d in range(1, 11)]    # volatile-down regime


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch) -> str:
    """Point FAISS artifacts at an isolated temp directory."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return str(tmp_path)


@pytest_asyncio.fixture
async def seeded_market(db_session: AsyncSession) -> None:
    stocks = [
        Stock(
            symbol=f"S{i}.NS",
            name=f"S{i}",
            sector="Technology",
            exchange="NSE",
            history_eligible=True,
        )
        for i in range(4)
    ]
    db_session.add_all(stocks)
    await db_session.flush()

    all_dates = A_DATES + B_DATES
    for si, stock in enumerate(stocks):
        close = 100.0 + si * 10
        for di, d in enumerate(all_dates):
            regime_a = d.month == 1
            close += 1.0 if regime_a else -1.0
            db_session.add(
                DailyPrice(stock_id=stock.id, date=d, open=close, high=close * 1.01,
                           low=close * 0.99, close=close, volume=1000)
            )
            if regime_a:
                db_session.add(Indicator(
                    stock_id=stock.id, date=d, rsi_14=58 + 0.3 * di,
                    ema_20=close * 0.99, ema_50=close * 0.97,
                    bb_upper=close * 1.02, bb_lower=close * 0.98,
                    atr_14=close * 0.01, macd_histogram=close * 0.003,
                ))
            else:
                db_session.add(Indicator(
                    stock_id=stock.id, date=d, rsi_14=38 + 0.3 * di,
                    ema_20=close * 1.01, ema_50=close * 1.03,
                    bb_upper=close * 1.04, bb_lower=close * 0.96,
                    atr_14=close * 0.03, macd_histogram=-close * 0.003,
                ))

    macro_stocks = [
        Stock(
            symbol=symbol,
            name=name,
            sector="Macro",
            industry=asset_class,
            exchange="GLOBAL",
            is_active=False,
        )
        for symbol, (name, asset_class) in MACRO_PROXIES.items()
    ]
    db_session.add_all(macro_stocks)
    await db_session.flush()
    for mi, stock in enumerate(macro_stocks):
        close = 70.0 + mi * 20
        for d in all_dates:
            close *= 1.002 if d.month == 1 else 0.997
            db_session.add(
                DailyPrice(
                    stock_id=stock.id,
                    date=d,
                    open=close,
                    high=close * 1.01,
                    low=close * 0.99,
                    close=close,
                    volume=0,
                )
            )
    await db_session.commit()
