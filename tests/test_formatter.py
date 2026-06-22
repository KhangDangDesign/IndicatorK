"""Tests for Telegram message formatting."""

from src.models import GuardrailsReport, PortfolioState, ProviderHealth, Recommendation, StrategyHealth, WeeklyPlan
from src.telegram.formatter import format_weekly_digest


def test_weekly_digest_shows_sell_recommendations_as_signals():
    plan = WeeklyPlan(
        generated_at="2026-06-22T14:59:41",
        strategy_id="regime_router_foundation",
        strategy_version="1.0.0",
        allocation_targets={"stock": 0.0, "bond_fund": 1.0},
        recommendations=[
            Recommendation(
                symbol="MWG",
                asset_class="stock",
                action="SELL",
                buy_zone_low=0.0,
                buy_zone_high=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_target_pct=0.0,
                rationale_bullets=["Bear regime: preserve capital and move to cash."],
            )
        ],
        market_regime="bear",
    )
    portfolio_state = PortfolioState(
        positions={},
        cash=10_000_000,
        total_value=10_000_000,
        allocation={"stock_pct": 0.0, "bond_fund_pct": 0.0, "cash_pct": 1.0},
        unrealized_pnl=0.0,
        realized_pnl=0.0,
    )
    guardrails = GuardrailsReport(
        generated_at="2026-06-22T14:59:46",
        provider_health=ProviderHealth(
            name="vnstock->http->cache",
            error_rate=0.0,
            missing_rate=0.0,
            last_success_at="2026-06-22T14:59:41",
        ),
        strategy_health=StrategyHealth(
            rolling_cagr=0.0,
            drawdown=0.0,
            turnover=0.0,
        ),
    )

    message = format_weekly_digest(plan, portfolio_state, guardrails)

    assert "🔴 SELL Signals (1)" in message
    assert "MWG" in message
    assert "Bear regime: preserve capital and move to cash." in message
