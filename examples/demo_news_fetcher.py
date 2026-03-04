#!/usr/bin/env python3
"""Demo script showing real news fetching for Vietnamese stock AI analysis.

This script demonstrates:
1. Fetching real news for Vietnamese stocks
2. Using cache to avoid repeated API calls
3. Fallback behavior when APIs are unavailable
4. Integration with the two-stage Groq scoring pipeline

Usage:
    python examples/demo_news_fetcher.py

    To clear cache and fetch fresh news:
    python examples/demo_news_fetcher.py --fresh

    To specify custom symbols:
    python examples/demo_news_fetcher.py --symbols VHM VIC VJC
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news_ai import fetch_recent_news, clear_cache, score_buy_potential

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def demo_fetch_news():
    """Demonstrate news fetching."""
    logger.info("=" * 80)
    logger.info("DEMO: Real News Fetching for Vietnamese Stock AI Analysis")
    logger.info("=" * 80)

    # Fetch news for common Vietnamese stocks
    symbols = ["STB", "VPB", "MWG", "VHM", "VIC"]
    logger.info(f"\nFetching news for symbols: {symbols}")

    try:
        news_items = fetch_recent_news(
            symbols=symbols,
            days_back=7,
            use_cache=True,
        )

        logger.info(f"\nSuccessfully fetched {len(news_items)} news items\n")

        # Display first 5 news items
        for idx, item in enumerate(news_items[:5], 1):
            print(f"\n--- News Item #{idx} ---")
            print(f"Title:       {item.get('title', 'N/A')}")
            print(f"Source:      {item.get('source', 'N/A')}")
            print(f"Published:   {item.get('published_at', 'N/A')}")
            print(f"Snippet:     {item.get('snippet', 'N/A')[:100]}...")
            if item.get('url'):
                print(f"URL:         {item.get('url')}")

        # Show cache stats
        cache_path = Path("data/news_cache.json")
        if cache_path.exists():
            with open(cache_path) as f:
                cache_data = json.load(f)
            logger.info(f"\nCache Status:")
            logger.info(f"  - Cached articles: {len(cache_data.get('articles', []))}")
            logger.info(f"  - Fetched at: {cache_data.get('fetched_at', 'Unknown')}")
            logger.info(f"  - Cache TTL: 24 hours")

        return news_items

    except Exception as e:
        logger.error(f"Failed to fetch news: {e}", exc_info=True)
        return []


def demo_scoring_pipeline(news_items):
    """Demonstrate two-stage scoring pipeline with real news."""
    if not news_items:
        logger.warning("No news items to score - skipping pipeline demo")
        return

    logger.info("\n" + "=" * 80)
    logger.info("DEMO: Two-Stage Groq Scoring Pipeline")
    logger.info("=" * 80)

    # Create a minimal weekly plan for demonstration
    demo_plan = {
        "recommendations": [
            {"symbol": "STB", "action": "BUY", "score": 7.5},
            {"symbol": "VPB", "action": "BUY", "score": 7.0},
            {"symbol": "MWG", "action": "HOLD", "score": 5.5},
            {"symbol": "VHM", "action": "HOLD", "score": 5.0},
            {"symbol": "VIC", "action": "HOLD", "score": 4.5},
        ]
    }

    # Save plan temporarily
    temp_plan_path = "data/demo_plan_temp.json"
    with open(temp_plan_path, "w") as f:
        json.dump(demo_plan, f, indent=2)

    logger.info(f"\nScoring {len(demo_plan['recommendations'])} symbols with {len(news_items)} news items...")
    logger.info(f"\nNews source breakdown:")
    sources = {}
    for item in news_items:
        source = item.get("source", "Unknown")
        sources[source] = sources.get(source, 0) + 1
    for source, count in sorted(sources.items()):
        logger.info(f"  - {source}: {count} articles")

    try:
        # Run scoring pipeline
        logger.info("\nRunning two-stage Groq pipeline:")
        logger.info("  Stage A: llama-3.1-8b-instant (scoring)")
        logger.info("  Stage B: llama-3.3-70b-versatile (validation)")

        scores = score_buy_potential(temp_plan_path, news_items)

        if scores.get("status") == "SUCCESS":
            logger.info(f"\nScoringSuccess! Results:")
            logger.info(f"  - Status: {scores['status']}")
            logger.info(f"  - Symbols analyzed: {scores.get('analyzed_symbols', 0)}")
            logger.info(f"  - Total news used: {scores.get('total_news', 0)}")

            # Save scores
            scores_path = Path("data/demo_news_scores.json")
            with open(scores_path, "w") as f:
                json.dump(scores, f, indent=2)
            logger.info(f"  - Results saved to: {scores_path}")

            # Display first score details
            symbol_scores = scores.get("symbol_scores", [])
            if symbol_scores:
                first_score = symbol_scores[0]
                logger.info(f"\nExample score for {first_score.get('symbol')}:")
                logger.info(f"  - Buy potential: {first_score.get('buy_potential_score', 'N/A')}/100")
                logger.info(f"  - Risk score: {first_score.get('risk_score', 'N/A')}/100")
                logger.info(f"  - Confidence: {first_score.get('confidence', 'N/A')}")
                logger.info(f"  - Horizon: {first_score.get('horizon', 'N/A')}")
        else:
            logger.warning(f"Scoring failed: {scores.get('status')}")
            logger.warning(f"This is normal if GROQ_API_KEY is not configured")
            logger.info(f"\nTo enable real scoring:")
            logger.info(f"  1. Set GROQ_API_KEY environment variable")
            logger.info(f"  2. Run the weekly workflow or this script again")

    except Exception as e:
        logger.error(f"Scoring pipeline error: {e}", exc_info=True)

    finally:
        # Cleanup
        if Path(temp_plan_path).exists():
            Path(temp_plan_path).unlink()


def main():
    """Run demo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear cache and fetch fresh news"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["STB", "VPB", "MWG", "VHM", "VIC"],
        help="Custom stock symbols to fetch news for"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days back to fetch news"
    )
    parser.add_argument(
        "--no-score",
        action="store_true",
        help="Skip the scoring pipeline demo"
    )

    args = parser.parse_args()

    # Clear cache if requested
    if args.fresh:
        logger.info("Clearing news cache...")
        clear_cache()

    # Fetch news
    news_items = demo_fetch_news()

    # Run scoring pipeline if news was fetched and not skipped
    if news_items and not args.no_score:
        demo_scoring_pipeline(news_items)

    logger.info("\n" + "=" * 80)
    logger.info("Demo Complete!")
    logger.info("=" * 80)
    logger.info("\nNext steps:")
    logger.info("  1. Set NEWS_API_KEY for better news coverage")
    logger.info("  2. Set GROQ_API_KEY to enable AI scoring")
    logger.info("  3. Run 'scripts/run_weekly.py' for full workflow")


if __name__ == "__main__":
    main()
