"""Deterministic screener execution and saved-screen orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.exceptions import SavedScreenNotFoundError
from app.discovery.models import SavedScreen
from app.discovery.parser import parse_screener_query
from app.discovery.repository import DiscoveryRepository
from app.discovery.schemas import (
    SavedScreenCreate,
    SavedScreenOut,
    ScreenerAST,
    ScreenerCondition,
    ScreenerQuery,
    ScreenerResult,
    ScreenerRow,
)
from app.market.repository import MarketRepository
from app.news.repository import NewsRepository
from config.settings import settings


def _signal(close: float | None, ema20: float | None, macd: float | None) -> str:
    if close is None or ema20 is None or macd is None:
        return "unavailable"
    if close > ema20 and macd > 0:
        return "bullish"
    if close < ema20 and macd < 0:
        return "bearish"
    return "neutral"


def _numeric(value: float | None, condition: ScreenerCondition) -> bool:
    if value is None:
        return False
    target = float(condition.value) if condition.value is not None else 0.0
    if condition.operator == "gt":
        return value > target
    if condition.operator == "gte":
        return value >= target
    if condition.operator == "lt":
        return value < target
    if condition.operator == "lte":
        return value <= target
    if condition.operator == "positive":
        return value > 0
    if condition.operator == "negative":
        return value < 0
    if condition.operator == "non_negative":
        return value >= 0
    if condition.operator == "between":
        return (
            condition.upper_value is not None and target <= value <= condition.upper_value
        )
    return False


def _matches(row: ScreenerRow, condition: ScreenerCondition) -> bool:
    if condition.field == "sector":
        return (
            row.sector is not None
            and str(condition.value).casefold() in row.sector.casefold()
        )
    if condition.field == "price_vs_ema20":
        return (
            row.close is not None
            and row.ema_20 is not None
            and (
                row.close > row.ema_20
                if condition.operator == "above"
                else row.close < row.ema_20
            )
        )
    if condition.field == "price_vs_ema50":
        return (
            row.close is not None
            and row.ema_50 is not None
            and (
                row.close > row.ema_50
                if condition.operator == "above"
                else row.close < row.ema_50
            )
        )
    if condition.field in {"signal_state", "regime_fit"}:
        return getattr(row, condition.field) == condition.value
    return _numeric(getattr(row, condition.field), condition)


def _explain(condition: ScreenerCondition) -> str:
    labels = {
        "sector": "Sector",
        "price_change_percent": "1-day price change",
        "rsi_14": "RSI 14",
        "price_vs_ema20": "Price vs EMA 20",
        "price_vs_ema50": "Price vs EMA 50",
        "macd_histogram": "MACD histogram",
        "volume_ratio": "Relative volume",
        "pe_ratio": "P/E",
        "eps": "EPS",
        "news_sentiment": "Recent news sentiment",
        "signal_state": "Signal state",
        "regime_fit": "Current regime fit",
    }
    if condition.operator == "between":
        value = f"{condition.value}–{condition.upper_value}"
    elif condition.value is None:
        value = condition.operator.replace("_", " ")
    else:
        value = f"{condition.operator.replace('_', ' ')} {condition.value}"
    return f"{labels[condition.field]}: {value}"


class DiscoveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DiscoveryRepository(db)
        self.market = MarketRepository(db)
        self.news = NewsRepository(db)

    async def screen(self, payload: ScreenerQuery) -> ScreenerResult:
        return await self.execute(payload.query, parse_screener_query(payload.query))

    async def execute(self, query: str, ast: ScreenerAST) -> ScreenerResult:
        stocks = await self.market.list_approved_equities(ast.universe)
        ids = [stock.id for stock in stocks]
        snapshots = await self.market.get_market_snapshots(ids, known_stocks=stocks)
        volumes = await self.market.get_latest_relative_volumes(ids)
        latest_date = await self.market.get_latest_active_price_date()
        sentiments = await self.news.get_latest_sentiment_map(
            recent_since=(
                latest_date - timedelta(days=settings.news_recent_window_days - 1)
            )
            if latest_date
            else None
        )
        provisional: list[ScreenerRow] = []
        for stock in stocks:
            snapshot = snapshots.get(stock.id)
            prices = list(snapshot.prices) if snapshot else []
            latest = prices[0] if prices else None
            prior = prices[1] if len(prices) > 1 else None
            change = (
                ((latest.close / prior.close - 1) * 100)
                if latest and prior and prior.close
                else None
            )
            indicator = snapshot.indicator if snapshot else None
            fundamental = stock.fundamentals
            state = _signal(
                latest.close if latest else None,
                indicator.ema_20 if indicator else None,
                indicator.macd_histogram if indicator else None,
            )
            provisional.append(
                ScreenerRow(
                    symbol=stock.symbol,
                    name=stock.name,
                    sector=stock.sector,
                    as_of=latest.date if latest else None,
                    close=latest.close if latest else None,
                    price_change_percent=change,
                    rsi_14=indicator.rsi_14 if indicator else None,
                    ema_20=indicator.ema_20 if indicator else None,
                    ema_50=indicator.ema_50 if indicator else None,
                    macd_histogram=indicator.macd_histogram if indicator else None,
                    volume_ratio=volumes.get(stock.id),
                    pe_ratio=fundamental.pe_ratio if fundamental else None,
                    eps=fundamental.eps if fundamental else None,
                    news_sentiment=sentiments.get(stock.id),
                    signal_state=state,
                    regime_fit="pending",
                )
            )
        available = [
            row.signal_state for row in provisional if row.signal_state != "unavailable"
        ]
        bullish = available.count("bullish")
        bearish = available.count("bearish")
        market_state = (
            "bullish"
            if bullish > bearish
            else "bearish"
            if bearish > bullish
            else "neutral"
        )
        rows = [
            row.model_copy(
                update={
                    "regime_fit": "aligned"
                    if row.signal_state == market_state
                    else "divergent"
                }
            )
            for row in provisional
        ]
        rows = [
            row
            for row in rows
            if all(_matches(row, condition) for condition in ast.conditions)
        ]
        rows.sort(key=lambda row: row.symbol)
        canonical = {
            "ast": ast.model_dump(mode="json"),
            "rows": [row.model_dump(mode="json") for row in rows],
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ScreenerResult(
            query=query,
            ast=ast,
            explanation=[_explain(c) for c in ast.conditions],
            rows=rows,
            result_hash=digest,
        )

    async def save(self, user_id: int, payload: SavedScreenCreate) -> SavedScreenOut:
        # Re-validate the original text and require the persisted AST to match it.
        parsed = parse_screener_query(payload.query_text)
        if parsed != payload.filter_ast:
            from app.discovery.exceptions import UnsupportedScreenerQueryError

            raise UnsupportedScreenerQueryError(["filter AST does not match query text"])
        screen = await self.repo.add(
            SavedScreen(
                user_id=user_id,
                name=payload.name.strip(),
                query_text=payload.query_text.strip(),
                filter_ast=parsed.model_dump(mode="json"),
            )
        )
        await self.db.commit()
        return SavedScreenOut.model_validate(screen)

    async def list_saved(self, user_id: int) -> list[SavedScreenOut]:
        return [
            SavedScreenOut.model_validate(item) for item in await self.repo.list(user_id)
        ]

    async def run_saved(self, user_id: int, screen_id: int) -> ScreenerResult:
        screen = await self.repo.get(user_id, screen_id)
        if screen is None:
            raise SavedScreenNotFoundError()
        return await self.execute(
            screen.query_text, ScreenerAST.model_validate(screen.filter_ast)
        )

    async def delete_saved(self, user_id: int, screen_id: int) -> None:
        screen = await self.repo.get(user_id, screen_id)
        if screen is None:
            raise SavedScreenNotFoundError()
        await self.repo.delete(screen)
        await self.db.commit()
