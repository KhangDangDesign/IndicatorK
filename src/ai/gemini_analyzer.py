"""Gemini API integration for AI-powered stock analysis and scoring.

Uses Google's Gemini free tier to provide:
  - Confidence scores (1-10) for each weekly recommendation
  - Brief Vietnamese-market-aware rationale per stock
  - Overall market context summary

Graceful degradation: all public functions return sensible defaults
if the API key is missing or a call fails. The system never breaks
without Gemini.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Gemini model for weekly stock analysis — using proven free tier model
_DEFAULT_MODEL = "gemini-2.0-flash"
_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
_TIMEOUT = 30  # seconds


@dataclass
class AIScore:
    """AI-generated score and rationale for a single recommendation."""
    symbol: str
    score: int  # 1-10 confidence
    rationale: str  # 1-2 sentence explanation
    risk_note: str = ""  # optional risk flag


@dataclass
class AIAnalysis:
    """Complete AI analysis for a weekly plan."""
    scores: dict[str, AIScore] = field(default_factory=dict)  # symbol -> AIScore
    market_context: str = ""  # overall VN market summary
    generated: bool = False  # True if AI actually ran


def get_api_keys() -> list[str]:
    """Read all available Gemini API keys from environment."""
    keys = []
    # Primary API key
    if key1 := os.environ.get("GEMINI_API_KEY"):
        keys.append(key1)
    # Secondary API key (for rate limit failover)
    if key2 := os.environ.get("GEMINI_API_KEY_2"):
        keys.append(key2)
    return keys


def get_api_key() -> Optional[str]:
    """Read primary Gemini API key from environment (legacy compatibility)."""
    keys = get_api_keys()
    return keys[0] if keys else None


def is_available() -> bool:
    """Check if Gemini integration is configured."""
    return bool(get_api_keys())


def _build_scoring_prompt(recommendations: list[dict], portfolio_summary: str) -> str:
    """Build the prompt for Gemini to score recommendations."""
    rec_lines = []
    for r in recommendations:
        rec_lines.append(
            f"- {r['symbol']}: {r['action']} | entry_type={r.get('entry_type', 'N/A')} | "
            f"entry={r.get('entry_price', 0):,.0f} | SL={r.get('stop_loss', 0):,.0f} | "
            f"TP={r.get('take_profit', 0):,.0f} | "
            f"rationale: {'; '.join(r.get('rationale_bullets', []))}"
        )
    rec_block = "\n".join(rec_lines)

    return f"""You are a Vietnamese stock market analyst. Analyze these weekly trading recommendations
and provide a confidence score (1-10) for each, plus a brief market context summary.

PORTFOLIO:
{portfolio_summary}

RECOMMENDATIONS:
{rec_block}

INSTRUCTIONS:
1. Score each recommendation 1-10 based on:
   - Technical setup quality (trend alignment, entry timing)
   - Risk/reward ratio (SL vs TP distance)
   - Vietnamese market context (sector trends, macro conditions)
   - Entry type suitability (breakout confirmation vs pullback value)

2. Provide a 1-sentence rationale for each score in Vietnamese or English.

3. Flag any significant risks (e.g., low liquidity, sector headwinds).

4. Write a 2-3 sentence overall Vietnamese market context summary.

Respond ONLY with valid JSON in this exact format:
{{
  "scores": {{
    "SYMBOL": {{
      "score": 7,
      "rationale": "Strong breakout with volume confirmation",
      "risk_note": ""
    }}
  }},
  "market_context": "Overall VN market summary here."
}}"""


def _call_gemini(prompt: str, api_keys: list[str]) -> Optional[dict]:
    """Make Gemini API calls with automatic failover between keys."""
    import requests

    url = _API_URL_TEMPLATE.format(model=_DEFAULT_MODEL)
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }

    for i, api_key in enumerate(api_keys):
        key_label = f"API key {i+1}/{len(api_keys)}"
        logger.info(f"Trying {key_label} (...{api_key[-8:]})")

        try:
            resp = requests.post(
                url,
                headers=headers,
                params={"key": api_key},
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()

            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
            logger.info(f"✅ {key_label} succeeded")
            return result

        except requests.exceptions.Timeout:
            logger.warning(f"⏰ {key_label} timeout after {_TIMEOUT}s")
            continue  # Try next API key

        except requests.exceptions.RequestException as e:
            # Detect specific rate limit error (429)
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                logger.warning(f"🚨 {key_label} RATE LIMIT (429) - switching to next API key")
                if i < len(api_keys) - 1:
                    logger.info(f"🔄 Automatically switching to API key {i+2}")
                    continue  # Try next API key
                else:
                    logger.warning("🚨 ALL API KEYS rate limited - AI analysis skipped")
                    logger.warning("⏰ This is normal for free tier. AI will work when quotas reset.")
                    logger.warning("✅ System deployment is working correctly, just hitting rate limits")
            else:
                logger.warning(f"❌ {key_label} request failed: {e}")
                continue  # Try next API key

        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.warning(f"❌ {key_label} failed to parse response: {e}")
            continue  # Try next API key

    # All API keys failed
    logger.warning("❌ All Gemini API keys exhausted - returning None")
    return None


def analyze_weekly_plan(
    plan_dict: dict,
    portfolio_summary: str = "",
) -> AIAnalysis:
    """Score all recommendations in a weekly plan using Gemini.

    Args:
        plan_dict: WeeklyPlan.to_dict() output
        portfolio_summary: short text describing portfolio state

    Returns:
        AIAnalysis with scores and market context.
        If API is unavailable or fails, returns an empty AIAnalysis
        with generated=False.
    """
    api_keys = get_api_keys()
    if not api_keys:
        logger.info("No Gemini API keys configured — skipping AI analysis")
        return AIAnalysis()

    recommendations = plan_dict.get("recommendations", [])
    if not recommendations:
        return AIAnalysis(generated=True, market_context="No recommendations to analyze.")

    prompt = _build_scoring_prompt(recommendations, portfolio_summary)
    logger.info(f"Starting Gemini analysis with {len(api_keys)} API key(s)")
    result = _call_gemini(prompt, api_keys)

    if result is None:
        logger.warning("Gemini analysis failed — returning empty analysis")
        return AIAnalysis()

    # Parse scores
    scores: dict[str, AIScore] = {}
    raw_scores = result.get("scores", {})
    for sym, data in raw_scores.items():
        sym = sym.upper().strip()
        score_val = data.get("score", 5)
        # Clamp to 1-10
        score_val = max(1, min(10, int(score_val)))
        scores[sym] = AIScore(
            symbol=sym,
            score=score_val,
            rationale=str(data.get("rationale", "")),
            risk_note=str(data.get("risk_note", "")),
        )

    market_context = str(result.get("market_context", ""))

    logger.info("Gemini scored %d/%d recommendations", len(scores), len(recommendations))
    return AIAnalysis(
        scores=scores,
        market_context=market_context,
        generated=True,
    )


def format_ai_section(analysis: AIAnalysis, recommendations: list[dict]) -> str:
    """Format AI analysis as a Telegram message section.

    Returns empty string if AI analysis was not generated.
    """
    if not analysis.generated:
        return ""

    lines = ["", "*🤖 AI Analysis*"]

    if analysis.market_context:
        lines.append(f"_{analysis.market_context}_")
        lines.append("")

    # Show scores for BUY recommendations first, then others
    buys = [r for r in recommendations if r.get("action") == "BUY"]
    others = [r for r in recommendations if r.get("action") != "BUY"]

    for r in buys + others:
        sym = r["symbol"]
        ai = analysis.scores.get(sym)
        if not ai:
            continue

        bar = _score_bar(ai.score)
        lines.append(f"  `{sym}` {bar} {ai.score}/10")
        if ai.rationale:
            lines.append(f"    {ai.rationale}")
        if ai.risk_note:
            lines.append(f"    ⚠ {ai.risk_note}")

    return "\n".join(lines)


def _score_bar(score: int) -> str:
    """Visual score indicator."""
    if score >= 8:
        return "🟢"
    if score >= 6:
        return "🔵"
    if score >= 4:
        return "🟡"
    return "🔴"
