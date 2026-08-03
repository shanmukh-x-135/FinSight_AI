"""Unit tests for the pure portfolio analytics against hand-computed values.

Reference portfolio (two holdings):
  H1: qty 10 @ 100, price 110 (prev 108), sector Tech,   ATR 5.5
  H2: qty  5 @ 200, price 180 (prev 185), sector Energy, ATR 9.0

Hand calculation:
  H1: mv=1100 cb=1000 pnl=+100 ret=+10%  daily=10*(110-108)=+20
  H2: mv= 900 cb=1000 pnl=-100 ret=-10%  daily= 5*(180-185)=-25
  total_value=2000 total_cost=2000 total_pnl=0 total_return=0%
  weights: 55% / 45%  → HHI=0.55²+0.45²=0.505  diversification=(1-0.505)*100=49.5
  daily_pnl=-5  yesterday=2005  daily%=-5/2005*100=-0.2494
  volatility = (5.5/110*1100 + 9/180*900)/2000 = (5%*1100 + 5%*900)/2000 = 5.0%
  health = 0.4*49.5 + 0.3*(100-55) + 0.3*clamp(50+0)=19.8+13.5+15 = 48.3
  risk = high (top weight 55% ≥ 50%)
"""

from __future__ import annotations

import pytest

from app.portfolio.analytics import HoldingInput, compute_portfolio_analytics

H1 = HoldingInput(
    id=1, symbol="AAA", name="Alpha", sector="Tech",
    quantity=10, avg_buy_price=100, current_price=110, previous_close=108, atr=5.5,
)
H2 = HoldingInput(
    id=2, symbol="BBB", name="Beta", sector="Energy",
    quantity=5, avg_buy_price=200, current_price=180, previous_close=185, atr=9.0,
)


def test_reference_portfolio_totals() -> None:
    a = compute_portfolio_analytics(1, "Ref", [H1, H2])
    assert a.total_value == pytest.approx(2000.0)
    assert a.total_cost == pytest.approx(2000.0)
    assert a.total_unrealized_pnl == pytest.approx(0.0)
    assert a.total_return_percent == pytest.approx(0.0)
    assert a.daily_pnl == pytest.approx(-5.0)
    assert a.daily_pnl_percent == pytest.approx(-0.2494, abs=1e-4)


def test_reference_portfolio_concentration_and_health() -> None:
    a = compute_portfolio_analytics(1, "Ref", [H1, H2])
    assert a.number_of_holdings == 2
    assert a.number_of_sectors == 2
    assert a.top_holding_weight_percent == pytest.approx(55.0)
    assert a.concentration_hhi == pytest.approx(0.505)
    assert a.diversification_score == pytest.approx(49.5)
    assert a.volatility_percent == pytest.approx(5.0)
    assert a.health_score == pytest.approx(48.3)
    assert a.risk_level == "high"


def test_reference_portfolio_sector_allocation_sorted() -> None:
    a = compute_portfolio_analytics(1, "Ref", [H1, H2])
    assert [s.sector for s in a.sector_allocation] == ["Tech", "Energy"]  # value desc
    assert a.sector_allocation[0].value == pytest.approx(1100.0)
    assert a.sector_allocation[0].weight_percent == pytest.approx(55.0)
    assert a.sector_allocation[1].weight_percent == pytest.approx(45.0)


def test_reference_per_holding_values() -> None:
    a = compute_portfolio_analytics(1, "Ref", [H1, H2])
    by_symbol = {h.symbol: h for h in a.holdings}
    assert by_symbol["AAA"].market_value == pytest.approx(1100.0)
    assert by_symbol["AAA"].unrealized_pnl == pytest.approx(100.0)
    assert by_symbol["AAA"].return_percent == pytest.approx(10.0)
    assert by_symbol["AAA"].daily_pnl == pytest.approx(20.0)
    assert by_symbol["AAA"].weight_percent == pytest.approx(55.0)
    assert by_symbol["BBB"].return_percent == pytest.approx(-10.0)
    assert by_symbol["BBB"].daily_pnl == pytest.approx(-25.0)


def test_empty_portfolio() -> None:
    a = compute_portfolio_analytics(9, "Empty", [])
    assert a.total_value == 0.0
    assert a.number_of_holdings == 0
    assert a.holdings == []
    assert a.sector_allocation == []
    assert a.health_score == 0.0
    assert a.risk_level == "low"
    assert a.diversification_score == 0.0


def test_single_holding_is_fully_concentrated() -> None:
    single = HoldingInput(
        id=1, symbol="AAA", name="Alpha", sector="Tech",
        quantity=10, avg_buy_price=100, current_price=110,
    )
    a = compute_portfolio_analytics(1, "One", [single])
    assert a.concentration_hhi == pytest.approx(1.0)
    assert a.diversification_score == pytest.approx(0.0)
    assert a.top_holding_weight_percent == pytest.approx(100.0)
    assert a.risk_level == "high"
    assert a.total_return_percent == pytest.approx(10.0)


def test_medium_risk_threshold() -> None:
    # Two holdings 40/60 → top weight 60 → high; make it 35/65? top 65 high.
    # Construct 3 holdings so top weight is ~40% → medium.
    holdings = [
        HoldingInput(id=1, symbol="A", name=None, sector="X",
                     quantity=1, avg_buy_price=100, current_price=100),   # mv 100
        HoldingInput(id=2, symbol="B", name=None, sector="Y",
                     quantity=1, avg_buy_price=100, current_price=80),    # mv 80
        HoldingInput(id=3, symbol="C", name=None, sector="Z",
                     quantity=1, avg_buy_price=100, current_price=70),    # mv 70
    ]
    a = compute_portfolio_analytics(1, "Med", holdings)
    # total 250; top weight = 100/250 = 40% → medium.
    assert a.top_holding_weight_percent == pytest.approx(40.0)
    assert a.risk_level == "medium"
