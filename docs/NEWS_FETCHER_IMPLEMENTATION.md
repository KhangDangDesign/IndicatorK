# Real News Fetching for Vietnamese Stock AI Analysis

## Overview

The news fetcher module enables the AI system to autonomously fetch recent news about Vietnamese stock symbols instead of using mock data. This integration allows for real-world market sentiment analysis and news-based buy potential scoring.

## Architecture

### Components

```
src/news_ai/
├── news_fetcher.py      # Main news fetching module
├── groq_buy_potential.py # Two-stage scoring pipeline
├── groq_client.py        # Groq API client
└── __init__.py          # Module exports
```

### Data Flow

```
fetch_recent_news()
    ↓
[Try Cache (24h TTL)]
    ↓
[Try NewsAPI.org]
    ↓
[Fallback: VnExpress Scraper]
    ↓
[Fallback: VietNamNet Scraper]
    ↓
[Default: Generic market news]
    ↓
Deduplication & Caching
    ↓
score_buy_potential()
    ↓
Stage A: llama-3.1-8b-instant (scoring)
    ↓
Stage B: llama-3.3-70b-versatile (validation)
    ↓
data/news_scores.json
```

## Features

### 1. Multiple News Sources

The fetcher tries sources in this priority order:

#### Primary: Cache (24-hour TTL)
- Stored in `data/news_cache.json`
- Prevents repeated API calls within 24 hours
- Reduces cost and improves performance

#### Secondary: NewsAPI.org
- Free tier available (limited without API key)
- Comprehensive coverage of worldwide financial news
- Supports custom queries for specific stocks
- Returns: title, description, URL, publication date, source

#### Tertiary: VnExpress Web Scraping
- Vietnamese language news source
- Focuses on business/stocks section
- Lightweight scraping using BeautifulSoup
- No API key required

#### Quaternary: VietNamNet Web Scraping
- Vietnamese language news source
- Alternative scraper for business news
- Same lightweight implementation

#### Fallback: Generic Market News
- Simple default news item if all sources fail
- Prevents crashes during workflow
- Returns minimal but valid news structure

### 2. Smart Caching

```json
{
  "articles": [
    {
      "id": "abc123def456",
      "title": "Vietnam stock market trends",
      "source": "NewsAPI",
      "snippet": "Article summary...",
      "published_at": "2026-03-04T10:00:00",
      "url": "https://example.com/article"
    }
  ],
  "fetched_at": "2026-03-04T11:00:00",
  "symbols": ["STB", "VPB", "MWG"],
  "days_back": 7
}
```

Features:
- 24-hour TTL (configurable)
- Automatic deduplication by URL
- Timestamp tracking
- Metadata about fetch parameters

### 3. Deduplication

Prevents duplicate articles by:
- Tracking article URLs
- MD5 hashing of article IDs
- Removing exact duplicates

### 4. Error Handling

Graceful degradation:
- API failures don't crash the workflow
- Missing API keys don't block execution
- Timeouts are caught and logged
- Falls back to next news source automatically

## API Reference

### `fetch_recent_news()`

Main entry point for fetching news.

```python
from src.news_ai import fetch_recent_news

articles = fetch_recent_news(
    symbols=["STB", "VPB", "MWG"],  # Optional, defaults to common symbols
    days_back=7,                     # Optional, number of days back
    use_cache=True                   # Optional, use cached news if valid
)
```

**Returns:**
```python
[
    {
        "id": "unique_hash",
        "title": "Article title",
        "source": "NewsAPI",
        "snippet": "Article summary",
        "published_at": "2026-03-04T10:00:00Z",
        "url": "https://example.com/article"  # Optional
    }
]
```

**Exception Handling:**
- Returns empty list if all sources fail
- Returns default market news as last resort
- Logs warnings for each failed source
- Does not raise exceptions

### `score_buy_potential()`

Two-stage Groq pipeline for news-based scoring.

```python
from src.news_ai import score_buy_potential

scores = score_buy_potential(
    weekly_plan_path="data/weekly_plan.json",
    news_items=articles
)
```

**Returns:**
```python
{
    "status": "SUCCESS",
    "analyzed_symbols": 5,
    "total_news": 15,
    "symbol_scores": [
        {
            "symbol": "STB",
            "buy_potential_score": 75,
            "risk_score": 35,
            "confidence": 0.85,
            "horizon": "1-4w",
            "key_bull_points": ["Point with evidence"],
            "key_risks": ["Risk with evidence"],
            "evidence": [{"id": "news_1", "supports": "bull"}]
        }
    ]
}
```

### `clear_cache()`

Clear the news cache.

```python
from src.news_ai import clear_cache

clear_cache()  # Deletes data/news_cache.json
```

## Integration with Weekly Workflow

The news fetcher is integrated into `scripts/run_weekly.py`:

```python
# Fetch real news about Vietnamese stocks
real_news = fetch_recent_news(
    symbols=all_symbols[:10],  # Top 10 symbols for API limits
    days_back=7,
    use_cache=True
)

# Pass to two-stage scoring pipeline
news_scores = score_buy_potential(temp_plan_path, real_news)

# Save results
Path("data/news_scores.json").write_text(json.dumps(news_scores, indent=2))
```

Key features:
- Automatic fallback to generic news if fetch fails
- Limits to 10 symbols to manage API rate limits
- Uses cache to avoid repeated calls
- Integrated with existing portfolio and risk analysis
- Results saved alongside other weekly outputs

## Configuration

### Environment Variables

**NEWS_API_KEY** (Optional)
```bash
export NEWS_API_KEY="your-newsapi-key"
```
- Get key from https://newsapi.org (free tier available)
- Without key: Limited to 5 requests/minute
- With key: 100 requests/minute (free tier)

**GROQ_API_KEY** (Required for scoring)
```bash
export GROQ_API_KEY="your-groq-key"
```
- Required for AI scoring pipeline
- Get key from https://console.groq.com

### Cache Configuration

In `src/news_ai/news_fetcher.py`:

```python
NEWS_CACHE_FILE = "data/news_cache.json"    # Cache location
CACHE_TTL_HOURS = 24                         # 24-hour TTL
REQUEST_TIMEOUT = 15.0                       # 15 second timeout
MAX_RETRIES = 2                              # 2 retry attempts
```

### Supported Vietnamese Symbols

Default symbols (from `VIETNAMESE_SYMBOLS`):
```
STB, VPB, MWG, VHM, VIC, VJC, FPT, VNM, CTG, BID,
BAC, EIB, VCB, TCB, HDB, ACB, ABBank, SBV, VRE, DHG
```

Add more by updating the `VIETNAMESE_SYMBOLS` set in `news_fetcher.py`.

## Usage Examples

### Example 1: Basic News Fetching

```python
from src.news_ai import fetch_recent_news
import logging

logging.basicConfig(level=logging.INFO)

# Fetch with defaults
articles = fetch_recent_news()

# Display results
print(f"Fetched {len(articles)} articles")
for article in articles[:3]:
    print(f"  - {article['title']}")
    print(f"    Source: {article['source']}")
```

### Example 2: Custom Symbols and Timeframe

```python
from src.news_ai import fetch_recent_news

# Fetch news for specific symbols
articles = fetch_recent_news(
    symbols=["VHM", "VIC"],
    days_back=14,  # Last 2 weeks
    use_cache=False  # Force fresh fetch
)

print(f"Found {len(articles)} articles about {len(articles)} stocks")
```

### Example 3: Full Scoring Pipeline

```python
from src.news_ai import fetch_recent_news, score_buy_potential
import json

# Fetch news
articles = fetch_recent_news()

# Load weekly plan (usually created by strategy engine)
with open("data/weekly_plan.json") as f:
    plan = json.load(f)

# Score with news
scores = score_buy_potential("data/weekly_plan.json", articles)

# Use scores
if scores["status"] == "SUCCESS":
    for score in scores["symbol_scores"]:
        symbol = score["symbol"]
        buy_score = score["buy_potential_score"]
        confidence = score["confidence"]
        print(f"{symbol}: {buy_score}/100 (confidence: {confidence:.1%})")
```

### Example 4: Demo Script

```bash
# Run the demo
python examples/demo_news_fetcher.py

# Fetch fresh news (clear cache)
python examples/demo_news_fetcher.py --fresh

# Custom symbols
python examples/demo_news_fetcher.py --symbols VHM VIC VJC

# Skip scoring (just fetch news)
python examples/demo_news_fetcher.py --no-score
```

## Testing

Run unit tests:

```bash
python3 -m pytest tests/test_news_fetcher.py -v
```

Test coverage:
- ✓ NewsItem data class
- ✓ Cache operations (load, save, validation)
- ✓ NewsAPI fetching (success, auth, rate limit, timeout)
- ✓ VnExpress scraping
- ✓ VietNamNet scraping
- ✓ Deduplication
- ✓ Fallback behavior
- ✓ Error handling
- ✓ Main fetch_recent_news() function
- ✓ Cache clearing

Total: 31 tests, 100% passing

## Performance Metrics

### Cache Hit Performance
- Cache valid: ~5ms (instant return)
- Cache invalid: ~500-2000ms (depends on news sources)

### API Response Times
- NewsAPI: ~200-500ms per query
- VnExpress scraper: ~300-500ms
- VietNamNet scraper: ~300-500ms

### Data Sizes
- Single news cache: ~20-50KB
- News scores JSON: ~5-20KB

### API Rate Limits
- NewsAPI free tier: 100 requests/month (5/min)
- NewsAPI paid: 100 requests/minute
- No rate limits for scraping (target sites don't use API)

## Troubleshooting

### No News Articles Fetched

**Symptoms:**
```
WARNING - No news articles fetched from any source
```

**Solutions:**
1. Check internet connection
2. Verify target websites are accessible
3. Install BeautifulSoup4 for scraping: `pip install beautifulsoup4`
4. Check if NEWS_API_KEY is set (optional but recommended)

### Rate Limiting

**Symptoms:**
```
WARNING - NewsAPI rate limit exceeded
```

**Solutions:**
1. Set NEWS_API_KEY for higher limits
2. Reduce number of symbols fetched
3. Use cache (24-hour TTL) to avoid repeated calls
4. Increase time between workflow runs

### Slow Performance

**Symptoms:**
```
Workflow taking too long to run
```

**Solutions:**
1. Check if cache is being used (should be ~5ms if valid)
2. Reduce symbols list in run_weekly.py
3. Increase REQUEST_TIMEOUT if network is slow
4. Use `--fresh` flag to skip fresh fetch and use cache

## Data Sources and Attribution

- **NewsAPI.org**: International financial news aggregator
- **VnExpress**: Vietnamese financial news
- **VietNamNet**: Vietnamese business news

All article URLs and sources are preserved in fetched data for proper attribution.

## Future Enhancements

Potential improvements:

1. **More Vietnamese News Sources**
   - Cafef.vn
   - Voiz.vn
   - TBDaily.vn

2. **NLP Analysis**
   - Sentiment analysis on Vietnamese text
   - Entity extraction (stock symbols, companies)
   - Keyword ranking

3. **Advanced Caching**
   - TTL per source
   - Selective invalidation
   - Priority caching

4. **API Alternatives**
   - Finnhub
   - Alpha Vantage
   - Yahoo Finance

5. **Real-time Updates**
   - WebSocket support
   - Event-driven fetching
   - Push notifications

## Support and Debugging

### Enable Debug Logging

```python
import logging

logging.getLogger("src.news_ai.news_fetcher").setLevel(logging.DEBUG)
```

### Inspect Cache

```bash
cat data/news_cache.json | jq .
```

### Check API Keys

```bash
echo "NEWS_API_KEY: $NEWS_API_KEY"
echo "GROQ_API_KEY: $GROQ_API_KEY"
```

### Run Individual Tests

```bash
# Test specific functionality
python3 -m pytest tests/test_news_fetcher.py::TestNewsApiFetcher -v

# Test with output capture
python3 -m pytest tests/test_news_fetcher.py -v -s
```

## References

- [NewsAPI.org Documentation](https://newsapi.org)
- [Groq API Documentation](https://console.groq.com/docs)
- [BeautifulSoup4 Documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Python Requests Library](https://docs.python-requests.org/)

## License

Part of the IndicatorK trading system. See main LICENSE file for details.
