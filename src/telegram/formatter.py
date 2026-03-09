"""Message templates — weekly digest, alerts, status (optional LLM scoring)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.models import Alert, GuardrailsReport, PortfolioState, WeeklyPlan

if TYPE_CHECKING:
    from src.ai.groq_analyzer import AIAnalysis

_ENTRY_ICON = {"breakout": "⬆", "pullback": "⬇"}
_ACTION_ICON = {"BUY": "🟢", "HOLD": "🔵", "REDUCE": "🟡", "SELL": "🔴"}
_CACHE_PATH = "data/prices_cache.json"


def _alloc_vnd(pct: float, total: float) -> int:
    """Round position allocation to nearest 100k VND."""
    return round(pct * total / 100_000) * 100_000


def _smart_format(value: float) -> str:
    """Smart formatting to show decimals when needed to distinguish values."""
    if value == 0:
        return "0"

    # For values > 1000, round to integer unless they need decimals for clarity
    if value >= 1000:
        rounded = round(value)
        # If rounding loses significant information, show 1 decimal place
        if abs(value - rounded) > value * 0.001:  # More than 0.1% difference
            return f"{value:,.1f}"
        return f"{rounded:,.0f}"

    # For values < 1000, show appropriate decimals
    if value >= 100:
        return f"{value:,.1f}"
    elif value >= 10:
        return f"{value:,.2f}"
    else:
        return f"{value:,.3f}"


def _load_cached_prices(symbols: list[str]) -> dict[str, float]:
    """Read last known prices from prices_cache.json."""
    p = Path(_CACHE_PATH)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return {
            sym: float(data[sym]["last_price"])
            for sym in symbols
            if sym in data and "last_price" in data[sym]
        }
    except Exception:
        return {}


def _zone_label(price: float, low: float, high: float) -> str:
    """Return a compact zone-distance label for a given price."""
    if low <= price <= high:
        return "✅ in zone"
    if price > high:
        pct = (price - high) / high * 100
        return f"⬆ {pct:.1f}% above zone"
    pct = (low - price) / low * 100
    return f"⬇ {pct:.1f}% below zone"


def _score_emoji(score: int) -> str:
    """Return color emoji for a 1-10 score."""
    if score >= 8:
        return "🟢"
    if score >= 6:
        return "🔵"
    if score >= 4:
        return "🟡"
    return "🔴"


def _calculate_unified_score(tech_score, news_data: dict | None) -> tuple[int | None, int | None, int | None]:
    """Calculate unified score from technical and news data.

    Formula: weighted average — tech*(1 - 0.4*conf) + news*0.4*conf
    Higher news confidence shifts weight toward news; lower keeps it near technical.

    Returns:
        (final, tech_s, news_s) — final is None if no data at all.
    """
    tech_s = getattr(tech_score, 'score', None) if tech_score else None
    news_s = None
    confidence = 0.5

    if news_data:
        buy_potential = news_data.get('buy_potential_score', 50)
        confidence = news_data.get('confidence', 0.5)
        news_s = max(1, min(10, round(buy_potential / 10)))

    if tech_s is not None and news_s is not None:
        combined = tech_s * (1 - 0.4 * confidence) + news_s * 0.4 * confidence
        final = max(1, min(10, round(combined)))
    elif tech_s is not None:
        final = tech_s
    elif news_s is not None:
        final = news_s
    else:
        return None, None, None

    return final, tech_s, news_s


def _clean_news_points(points: list[str], limit: int) -> list[str]:
    """Strip article ID references from news bullet points."""
    import re
    result = []
    for point in points[:limit]:
        clean = re.sub(r'\s*\(ID:\s*[^)]+\)', '', point.strip())
        if clean and len(clean) > 10:
            result.append(clean)
    return result


def _format_unified_analysis(ai_analysis, plan, recommendations) -> str:
    """Create unified analysis combining technical AI + news insights."""
    lines = ["", "*📊 Market Analysis*"]

    # Get technical analysis scores
    tech_scores = {}
    market_context = ""
    if ai_analysis and ai_analysis.generated:
        tech_scores = ai_analysis.scores if hasattr(ai_analysis, 'scores') else {}
        market_context = ai_analysis.market_context if hasattr(ai_analysis, 'market_context') else ""

    # Get news analysis scores
    news_scores = {}
    if hasattr(plan, 'news_analysis') and plan.news_analysis and plan.news_analysis.get('symbol_scores'):
        for score_data in plan.news_analysis.get('symbol_scores', []):
            symbol = score_data.get('symbol')
            if symbol:
                news_scores[symbol] = score_data

    if market_context:
        lines.append(f"_{market_context}_")
        lines.append("")

    for rec in recommendations[:6]:
        symbol = rec.symbol if hasattr(rec, 'symbol') else rec.get('symbol')
        if not symbol:
            continue

        tech_score = tech_scores.get(symbol)
        news_data = news_scores.get(symbol)

        final_score, _tech_s, _news_s = _calculate_unified_score(tech_score, news_data)
        if final_score is None:
            continue

        lines.append(f"  `{symbol}` {_score_emoji(final_score)} {final_score}/10")

        if tech_score:
            rationale = getattr(tech_score, 'rationale', '')
            if rationale:
                lines.append(f"    📊 Technical: {rationale}")

        news_content = []
        if news_data:
            for pt in _clean_news_points(news_data.get('key_bull_points', []), 2):
                news_content.append(f"📈 {pt}")
            for pt in _clean_news_points(news_data.get('key_risks', []), 1):
                news_content.append(f"⚠ {pt}")
            for line in news_content:
                lines.append(f"    {line}")

        tech_risk = getattr(tech_score, 'risk_note', '') if tech_score else ''
        if tech_risk and not any("⚠" in line for line in news_content):
            lines.append(f"    ⚠ Risk: {tech_risk}")

        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_ai_analysis_message(plan: WeeklyPlan, ai_analysis: AIAnalysis | None = None) -> str:
    """Format standalone AI analysis Telegram message with technical + news sections.

    Message structure:
      1. Technical Analysis — Groq scores with rationale/risk per stock
      2. News Analysis     — buy potential scores with key bull/risk points
      3. Summary Scores    — combined score (shared _calculate_unified_score formula)

    Returns empty string if no analysis data is available.
    """
    has_tech = bool(ai_analysis and ai_analysis.generated and ai_analysis.scores)
    has_news = bool(
        hasattr(plan, 'news_analysis')
        and plan.news_analysis
        and plan.news_analysis.get('symbol_scores')
    )

    if not has_tech and not has_news:
        return ""

    date_str = plan.generated_at[:10] if plan.generated_at else ""
    lines = [
        "*🤖 AI Market Analysis*",
        f"📅 {date_str}",
        "",
    ]

    rec_symbols = [r.symbol for r in plan.recommendations] if plan.recommendations else []

    tech_scores = {}
    market_context = ""
    if has_tech:
        tech_scores = ai_analysis.scores if hasattr(ai_analysis, 'scores') else {}
        market_context = ai_analysis.market_context if hasattr(ai_analysis, 'market_context') else ""

    news_scores: dict = {}
    if has_news:
        for score_data in plan.news_analysis.get('symbol_scores', []):
            symbol = score_data.get('symbol')
            if symbol:
                news_scores[symbol] = score_data

    if market_context:
        lines.append(f"_{market_context}_")
        lines.append("")

    # --- Technical Analysis Section ---
    if tech_scores:
        lines.append("*📊 Technical Analysis*")
        lines.append("")
        for sym in rec_symbols[:8]:
            score = tech_scores.get(sym)
            if not score:
                continue
            s = getattr(score, 'score', 5)
            lines.append(f"  `{sym}` {_score_emoji(s)} {s}/10")
            rationale = getattr(score, 'rationale', '')
            if rationale:
                lines.append(f"    {rationale}")
            risk_note = getattr(score, 'risk_note', '')
            if risk_note:
                lines.append(f"    ⚠ {risk_note}")
            lines.append("")

    # --- News Analysis Section ---
    if news_scores:
        lines.append("*📰 News Analysis*")
        lines.append("")
        for sym in rec_symbols[:8]:
            news_data = news_scores.get(sym)
            if not news_data:
                continue
            _final, _tech_s, news_s = _calculate_unified_score(None, news_data)
            if news_s is None:
                continue
            lines.append(f"  `{sym}` {_score_emoji(news_s)} {news_s}/10")
            for pt in _clean_news_points(news_data.get('key_bull_points', []), 2):
                lines.append(f"    📈 {pt}")
            for pt in _clean_news_points(news_data.get('key_risks', []), 1):
                lines.append(f"    ⚠ {pt}")
            lines.append("")

    # --- Summary Scores (canonical combined formula) ---
    lines.append("*🎯 Summary Scores*")
    lines.append("")
    for sym in rec_symbols[:8]:
        tech_score = tech_scores.get(sym) if tech_scores else None
        news_data = news_scores.get(sym)
        final, tech_s, news_s = _calculate_unified_score(tech_score, news_data)
        if final is None:
            continue

        parts = []
        if tech_s is not None:
            parts.append(f"Tech {tech_s}")
        if news_s is not None:
            parts.append(f"News {news_s}")
        detail = " | ".join(parts)
        lines.append(f"  `{sym}` {_score_emoji(final)} *{final}/10* ({detail})")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_weekly_digest(
    plan: WeeklyPlan,
    portfolio_state: PortfolioState,
    guardrails: GuardrailsReport | None,
    ai_analysis: AIAnalysis | None = None,
    include_analysis: bool = False,
) -> str:
    """Format the weekly digest Telegram message.

    AI analysis is sent as a separate message by run_ai_analysis.py.
    Pass include_analysis=True only when you explicitly want it inline.
    """
    total = portfolio_state.total_value

    # Add market regime indicator
    regime_emoji = {"bull": "🐂", "bear": "🐻", "sideways": "🦀"}.get(plan.market_regime, "📊")
    regime_text = f" — {regime_emoji} {plan.market_regime.upper()}" if plan.market_regime else ""

    lines = [
        f"📊 *Weekly Plan — S1 v{plan.strategy_version}*{regime_text}",
        f"📅 {plan.generated_at[:10]}  💰 {total:,.0f} ₫",
        "",
    ]

    buys = [r for r in plan.recommendations if r.action == "BUY"][:10]
    if buys:
        lines.append(f"*🟢 BUY Signals ({len(buys)})*")
        lines.append("")
        for r in buys:
            icon = _ENTRY_ICON.get(r.entry_type, "·")
            vnd = _alloc_vnd(r.position_target_pct, total) if r.position_target_pct and total else 0
            alloc_str = f" — {vnd:,.0f} ₫" if vnd else ""
            lines.append(f"  📈 `{r.symbol}` {icon} {r.entry_type.capitalize()}{alloc_str}")


            lines.append(f"    🎯 Entry: {r.entry_price:,.0f}")
            lines.append(f"    📊 Zone: {_smart_format(r.buy_zone_low)}–{_smart_format(r.buy_zone_high)}")
            lines.append(f"    🛡️ SL {_smart_format(r.stop_loss)} | TP {_smart_format(r.take_profit)}")
            lines.append("")

    # Simplified - treat all held positions the same
    holds = [r for r in plan.recommendations if r.action in ("HOLD", "REDUCE", "SELL")]
    if holds:
        lines.append("*📋 Open Positions — Alert Monitoring*")
        lines.append("")

        # Load current prices for better context
        cached = _load_cached_prices([r.symbol for r in holds])

        for r in holds:

            # Show current price + P&L if available
            current = cached.get(r.symbol)

            # Use actual portfolio entry price, not plan entry price
            portfolio_pos = portfolio_state.positions.get(r.symbol)
            if current and portfolio_pos and portfolio_pos.avg_cost > 0:
                # Handle potential units mismatch - portfolio might use different scale
                entry_price = portfolio_pos.avg_cost
                # If entry price seems to be in different units (e.g., 88 vs 88000), adjust
                if entry_price < 1000 and current > 1000:
                    entry_price *= 1000  # Convert portfolio price to same units as current price

                pnl_pct = ((current - entry_price) / entry_price) * 100
                status_line = f"  📊 `{r.symbol}` @ {current:,.0f} ({pnl_pct:+.1f}%)"
            else:
                status_line = f"  📊 `{r.symbol}` Monitoring"

            lines.append(status_line)

            # Clean exit alert format

            tp_str = f"TP {_smart_format(r.take_profit)}" if r.take_profit else ""
            sl_str = f"SL {_smart_format(r.stop_loss)}" if r.stop_loss else ""
            exit_levels = " | ".join(filter(None, [sl_str, tp_str]))

            lines.append(f"    🔔 Exit alerts: {exit_levels}")
            lines.append("")  # Spacing between positions

        # Remove extra line at end
        if lines and lines[-1] == "":
            lines.pop()

    alloc = portfolio_state.allocation
    targets = plan.allocation_targets
    lines.append("*💼 Portfolio*")
    lines.append(
        f"  Stock {alloc.get('stock_pct', 0):.0%}  "
        f"Bond {alloc.get('bond_fund_pct', 0):.0%}  "
        f"Cash {alloc.get('cash_pct', 0):.0%}"
    )
    lines.append(
        f"  Target → Stock {targets.get('stock', 0):.0%}  "
        f"Bond {targets.get('bond_fund', 0):.0%}"
    )

    # Only show guardrails when there are meaningful warnings
    if guardrails and guardrails.recommendations and len(guardrails.recommendations) > 0:
        # Filter out trivial strategy switch recommendations (e.g., -0.00% differences)
        meaningful_recs = []
        for rec in guardrails.recommendations:
            if "SWITCH_STRATEGY" in rec and "-0.0" in rec:
                # Skip trivial strategy switch recommendations near zero
                continue
            meaningful_recs.append(rec)

        if meaningful_recs:
            lines.append("")
            lines.append("*⚠️ Alerts*")
            for rec in meaningful_recs:
                lines.append(f"  {rec}")

    # AI analysis is sent separately — only include if explicitly requested
    if include_analysis and (ai_analysis or (hasattr(plan, 'news_analysis') and plan.news_analysis)):
        unified_section = _format_unified_analysis(ai_analysis, plan, plan.recommendations)
        if unified_section:
            lines.append(unified_section)

    return "\n".join(lines)


def format_alert(alert: Alert, portfolio_state: PortfolioState | None = None) -> str:
    """Format price alert with clear action guidance."""

    if alert.alert_type == "STOP_LOSS_HIT":
        lines = [
            f"🔴 **STOP LOSS HIT**",
            f"`{alert.symbol}` — Price hit {alert.current_price:,.0f}",
            f"💡 *SL threshold: {alert.threshold:,.0f}*"
        ]

        # Add helpful P&L context
        if portfolio_state and alert.symbol in portfolio_state.positions:
            pos = portfolio_state.positions[alert.symbol]
            pnl_pct = ((alert.current_price - pos.avg_cost) / pos.avg_cost) * 100
            pnl_vnd = (alert.current_price - pos.avg_cost) * pos.qty

            lines.extend([
                "",
                f"📈 **Trade Summary:**",
                f"Entry: {pos.avg_cost:,.0f} → Current: {alert.current_price:,.0f}",
                f"P&L: {pnl_pct:+.1f}% ({pnl_vnd:+,.0f} ₫)"
            ])

        return "\n".join(lines)

    if alert.alert_type == "TAKE_PROFIT_HIT":
        lines = [
            f"🟢 **TAKE PROFIT HIT**",
            f"`{alert.symbol}` — Price hit {alert.current_price:,.0f}",
            f"🎯 *TP threshold: {alert.threshold:,.0f}*"
        ]

        if portfolio_state and alert.symbol in portfolio_state.positions:
            pos = portfolio_state.positions[alert.symbol]
            pnl_pct = ((alert.current_price - pos.avg_cost) / pos.avg_cost) * 100
            pnl_vnd = (alert.current_price - pos.avg_cost) * pos.qty

            lines.extend([
                "",
                f"📈 **Trade Summary:**",
                f"Entry: {pos.avg_cost:,.0f} → Current: {alert.current_price:,.0f}",
                f"P&L: +{pnl_pct:.1f}% (+{pnl_vnd:,.0f} ₫)"
            ])

        return "\n".join(lines)

    if alert.alert_type == "ENTERED_BUY_ZONE":
        return (
            f"🔵 **BUY ZONE ENTRY**\n"
            f"`{alert.symbol}` — Entered buy zone\n"
            f"💡 *Current: {alert.current_price:,.0f} | Zone: ≥ {alert.threshold:,.0f}*\n"
            f"\n"
            f"📋 Check /plan for entry details"
        )

    # Fallback
    return f"🔔 **{alert.alert_type}** `{alert.symbol}`: {alert.current_price:,.0f}"


def format_status(state: PortfolioState) -> str:
    """Format portfolio status for /status command."""
    lines = ["*💼 Portfolio Status*", ""]

    if not state.positions:
        lines.append("No open positions.")
    else:
        lines.append("*Positions*")
        for sym, pos in sorted(state.positions.items()):
            pnl = pos.unrealized_pnl or 0
            lines.append(
                f"  `{sym}`: {pos.qty:,.0f} @ {pos.avg_cost:,.0f}"
                f" → {pos.current_price:,.0f}  PnL {pnl:+,.0f}"
            )

    lines.append("")
    lines.append(f"Total {state.total_value:,.0f} ₫  Cash {state.cash:,.0f}")
    lines.append(
        f"PnL  Unrealized {state.unrealized_pnl:+,.0f}  "
        f"Realized {state.realized_pnl:+,.0f}"
    )
    lines.append("")
    alloc = state.allocation
    lines.append(
        f"Stock {alloc.get('stock_pct', 0):.0%}  "
        f"Bond {alloc.get('bond_fund_pct', 0):.0%}  "
        f"Cash {alloc.get('cash_pct', 0):.0%}"
    )
    return "\n".join(lines)


def format_plan_summary(plan_data: dict, total_value: float = 0.0, portfolio_state=None) -> str:
    """Format weekly plan for /plan command with cached current prices and accurate P&L."""
    date_str = plan_data.get("generated_at", "?")[:10]
    balance_str = f"  💰 {total_value:,.0f} ₫" if total_value else ""
    lines = [
        f"📊 *{plan_data.get('strategy_id', '?')} v{plan_data.get('strategy_version', '?')}*",
        f"📅 {date_str}{balance_str}",
        "",
    ]

    recs = plan_data.get("recommendations", [])
    if not recs:
        lines.append("No recommendations.")
        return "\n".join(lines)

    cached = _load_cached_prices([r["symbol"] for r in recs])

    buys = [r for r in recs if r.get("action") == "BUY"]
    others = [r for r in recs if r.get("action") != "BUY"]

    if buys:
        lines.append(f"*🟢 BUY Signals ({len(buys)})*")
        lines.append("")
        for r in buys:
            sym = r["symbol"]
            icon = _ENTRY_ICON.get(r.get("entry_type", ""), "·")
            entry = r.get("entry_price", 0)
            pct = r.get("position_target_pct", 0)
            vnd = _alloc_vnd(pct, total_value) if pct and total_value else 0
            alloc_str = f" — {vnd:,.0f} ₫" if vnd else ""

            lines.append(f"  📈 `{sym}` {icon} {r.get('entry_type','').capitalize()}{alloc_str}")

            now = cached.get(sym)
            if now:
                label = _zone_label(now, r.get("buy_zone_low", 0), r.get("buy_zone_high", 0))
                lines.append(f"    📊 Now {now:,.0f}  {label}")

            lines.append(f"    🎯 Entry: {entry:,.0f}")
            lines.append(f"    📊 Zone: {_smart_format(r.get('buy_zone_low', 0))}–{_smart_format(r.get('buy_zone_high', 0))}")
            lines.append(f"    🛡️ SL {_smart_format(r.get('stop_loss', 0))} | TP {_smart_format(r.get('take_profit', 0))}")
            lines.append("")

    if others:
        lines.append("")
        lines.append("*📋 Open Positions — Alert Monitoring*")
        lines.append("")

        for r in others:
            sym = r["symbol"]

            # Show current price with accurate P&L using actual portfolio entry prices
            now = cached.get(sym)

            # Use actual portfolio entry price, not plan entry price (FIXED BUG #3)
            portfolio_pos = portfolio_state.positions.get(sym) if portfolio_state else None
            if now and portfolio_pos and portfolio_pos.avg_cost > 0:
                actual_entry = portfolio_pos.avg_cost
                pnl_pct = ((now - actual_entry) / actual_entry) * 100
                status_line = f"  📊 `{sym}` @ {now:,.0f} ({pnl_pct:+.1f}%)"
            elif now and r.get("entry_price", 0) > 0:
                # Fallback to plan entry_price if portfolio_state unavailable
                pnl_pct = ((now - r["entry_price"]) / r["entry_price"]) * 100
                status_line = f"  📊 `{sym}` @ {now:,.0f} ({pnl_pct:+.1f}%) [plan-entry]"
            else:
                now_str = f" — now {now:,.0f}" if now else ""
                status_line = f"  📊 `{sym}` Monitoring{now_str}"

            lines.append(status_line)

            # Exit levels
            tp = r.get("take_profit", 0)
            sl = r.get("stop_loss", 0)
            tp_str = f"TP {_smart_format(tp)}" if tp else ""
            sl_str = f"SL {_smart_format(sl)}" if sl else ""
            exit_levels = " | ".join(filter(None, [sl_str, tp_str]))

            lines.append(f"    🔔 Exit alerts: {exit_levels}")
            lines.append("")

    # Intentional: /plan is an on-demand query so we show cached AI inline here.
    # The weekly push notification omits AI (sent as a separate message by ai_analysis workflow).
    ai_analysis = plan_data.get("ai_analysis")
    if ai_analysis:
        lines.append("")
        lines.append("*🤖 AI Analysis*")

        # Market context
        if ai_analysis.get("market_context"):
            lines.append(f"_{ai_analysis['market_context']}_")
            lines.append("")

        if ai_analysis.get("generated"):
            # Normal AI analysis with scores
            ai_scores = ai_analysis.get("scores", {})
            for r in recs[:5]:  # Limit to first 5 recommendations
                sym = r["symbol"]
                ai_score = ai_scores.get(sym)
                if ai_score:
                    score = ai_score.get("score", 5)
                    rationale = ai_score.get("rationale", "")
                    risk_note = ai_score.get("risk_note", "")

                    lines.append(f"  `{sym}` {_score_emoji(score)} {score}/10")
                    if rationale:
                        lines.append(f"    {rationale}")
                    if risk_note:
                        lines.append(f"    ⚠ {risk_note}")
        else:
            # Rate limit or API not configured notice
            if ai_analysis.get("notice"):
                lines.append(f"{ai_analysis['notice']}")
            lines.append("")

    return "\n".join(lines)
