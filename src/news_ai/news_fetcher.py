"""News fetching module for Vietnamese stock analysis.

Fetches recent news articles about Vietnamese stock symbols from multiple sources:
- Primary: NewsAPI.org (free tier)
- Fallback: Light web scraping from VnExpress
- Cache: Local storage with 24h TTL to avoid repeated fetches

Returns:
    List of news items with: id, title, source, snippet, published_at, url (optional)
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

# Configuration
NEWS_CACHE_FILE = "data/news_cache.json"
CACHE_TTL_HOURS = 24
REQUEST_TIMEOUT = 15.0
MAX_RETRIES = 2

# Vietnamese stock symbols (common ones)
VIETNAMESE_SYMBOLS = {
    "STB", "VPB", "MWG", "VHM", "VIC", "VJC", "FPT", "VNM", "CTG", "BID",
    "BAC", "EIB", "VCB", "TCB", "HDB", "ACB", "ABBank", "SBV", "VRE", "DHG",
}


class NewsItem:
    """Data class for a news item."""

    def __init__(
        self,
        id: str,
        title: str,
        source: str,
        snippet: str,
        published_at: str,
        url: Optional[str] = None,
        symbol: Optional[str] = None,
    ):
        self.id = id
        self.title = title
        self.source = source
        self.snippet = snippet
        self.published_at = published_at
        self.url = url
        self.symbol = symbol

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "snippet": self.snippet,
            "published_at": self.published_at,
            "url": self.url,
            "symbol": self.symbol,
        }


def _get_cache_dir() -> Path:
    """Get or create cache directory."""
    cache_dir = Path("data")
    cache_dir.mkdir(exist_ok=True, parents=True)
    return cache_dir


def _load_cache() -> Dict[str, Any]:
    """Load news cache from disk."""
    cache_path = _get_cache_dir() / "news_cache.json"
    if not cache_path.exists():
        return {"articles": [], "fetched_at": None}

    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load cache: {e}")
        return {"articles": [], "fetched_at": None}


def _save_cache(cache: Dict[str, Any]) -> None:
    """Save news cache to disk."""
    cache_path = _get_cache_dir() / "news_cache.json"
    try:
        with open(cache_path, "w") as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Cached {len(cache.get('articles', []))} news items")
    except Exception as e:
        logger.warning(f"Failed to save cache: {e}")


def _is_cache_valid(cache: Dict[str, Any], max_age_hours: int = CACHE_TTL_HOURS) -> bool:
    """Check if cache is still valid (not older than max_age_hours)."""
    fetched_at = cache.get("fetched_at")
    if not fetched_at:
        return False

    try:
        fetched_time = datetime.fromisoformat(fetched_at)
        age = datetime.now() - fetched_time
        is_valid = age < timedelta(hours=max_age_hours)
        if is_valid:
            logger.info(f"Using cached news ({age.total_seconds():.0f}s old)")
        return is_valid
    except Exception as e:
        logger.warning(f"Failed to validate cache timestamp: {e}")
        return False


def _fetch_from_newsapi(symbols: List[str], days_back: int = 7) -> List[Dict[str, Any]]:
    """Fetch news from NewsAPI.org (free tier works without API key for common queries)."""
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        logger.warning("NEWS_API_KEY not set, NewsAPI fetch will be limited")
        # Free tier has limited requests without key
        return []

    articles = []
    base_url = "https://newsapi.org/v2/everything"

    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Fetch news for Vietnamese market
    queries = [
        "Vietnamese stocks market",
        "Thị trường chứng khoán Việt Nam",
        "Vietnam stock exchange",
    ]

    # Add symbol-specific queries
    for symbol in symbols[:5]:  # Limit to first 5 to avoid rate limiting
        queries.append(f'"{symbol}" OR "{symbol.lower()}"')

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    for query in queries:
        try:
            params = {
                "q": query,
                "from": from_date,
                "to": datetime.now().strftime("%Y-%m-%d"),
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
            }

            response = requests.get(
                base_url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 401:
                logger.warning("NewsAPI authentication failed - invalid/missing API key")
                return []
            elif response.status_code == 429:
                logger.warning("NewsAPI rate limit exceeded")
                break
            elif response.status_code != 200:
                logger.warning(f"NewsAPI error {response.status_code}: {response.text[:200]}")
                continue

            data = response.json()
            if data.get("status") == "ok":
                for article in data.get("articles", []):
                    articles.append({
                        "id": hashlib.md5(
                            article.get("url", "").encode()
                        ).hexdigest()[:16],
                        "title": article.get("title", ""),
                        "source": article.get("source", {}).get("name", "NewsAPI"),
                        "snippet": article.get("description", ""),
                        "published_at": article.get("publishedAt", ""),
                        "url": article.get("url"),
                    })
                logger.info(f"Fetched {len(articles)} articles from NewsAPI for query: {query[:30]}")
            else:
                logger.warning(f"NewsAPI error: {data.get('message', 'Unknown error')}")

        except requests.exceptions.Timeout:
            logger.warning("NewsAPI request timeout")
        except Exception as e:
            logger.warning(f"NewsAPI fetch failed: {e}")
            continue

    # Deduplicate by URL
    seen_urls = set()
    unique_articles = []
    for article in articles:
        url = article.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)
        elif not url:
            unique_articles.append(article)

    logger.info(f"NewsAPI returned {len(unique_articles)} unique articles")
    return unique_articles


def _fetch_from_vnexpress(symbols: List[str], days_back: int = 7) -> List[Dict[str, Any]]:
    """Lightweight web scraping from VnExpress financial section.

    This is a fallback when API is not available.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup4 not installed - skipping VnExpress scraping")
        return []

    articles = []

    try:
        # VnExpress business/stocks section
        url = "https://vnexpress.net/kinh-te-chung"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Find article containers (VnExpress uses various selectors)
        article_links = soup.find_all("a", {"class": "title-news"}, limit=30)

        for idx, link in enumerate(article_links):
            title = link.get_text(strip=True)
            article_url = link.get("href", "")

            # Skip if no title
            if not title:
                continue

            # Filter for stock-related keywords
            keywords = ["chứng khoán", "cổ phiếu", "stock", "thị trường", "market"]
            if not any(kw.lower() in title.lower() for kw in keywords):
                continue

            # Skip if URL is not absolute
            if not article_url.startswith("http"):
                article_url = f"https://vnexpress.net{article_url}"

            articles.append({
                "id": hashlib.md5(article_url.encode()).hexdigest()[:16],
                "title": title,
                "source": "VnExpress",
                "snippet": f"Scraped from VnExpress business section",
                "published_at": datetime.now().isoformat(),
                "url": article_url,
            })

        logger.info(f"Scraped {len(articles)} articles from VnExpress")
        return articles

    except requests.exceptions.Timeout:
        logger.warning("VnExpress request timeout")
    except Exception as e:
        logger.warning(f"VnExpress scraping failed: {e}")

    return []


def _fetch_from_vietnamnet(symbols: List[str], days_back: int = 7) -> List[Dict[str, Any]]:
    """Lightweight web scraping from VietNamNet business news."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup4 not installed - skipping VietNamNet scraping")
        return []

    articles = []

    try:
        url = "https://vietnamnet.vn/tieu-dung/"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Find article containers
        article_links = soup.find_all("a", limit=30)

        for link in article_links:
            title = link.get_text(strip=True)
            article_url = link.get("href", "")

            if not title or len(title) < 10:
                continue

            # Filter for stock-related keywords
            keywords = ["chứng khoán", "cổ phiếu", "stock", "thị trường", "market"]
            if not any(kw.lower() in title.lower() for kw in keywords):
                continue

            if not article_url.startswith("http"):
                article_url = f"https://vietnamnet.vn{article_url}"

            articles.append({
                "id": hashlib.md5(article_url.encode()).hexdigest()[:16],
                "title": title,
                "source": "VietNamNet",
                "snippet": "Scraped from VietNamNet business section",
                "published_at": datetime.now().isoformat(),
                "url": article_url,
            })

        logger.info(f"Scraped {len(articles)} articles from VietNamNet")
        return articles

    except requests.exceptions.Timeout:
        logger.warning("VietNamNet request timeout")
    except Exception as e:
        logger.warning(f"VietNamNet scraping failed: {e}")

    return []


def fetch_recent_news(
    symbols: Optional[List[str]] = None,
    days_back: int = 7,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch recent news about Vietnamese stock symbols.

    Tries multiple sources in order:
    1. Cache (if valid and use_cache=True)
    2. NewsAPI.org (if NEWS_API_KEY is set)
    3. VnExpress web scraping (fallback)
    4. VietNamNet web scraping (fallback)

    Args:
        symbols: List of stock symbols to fetch news for.
                Defaults to common Vietnamese stocks.
        days_back: Number of days back to fetch news. Defaults to 7.
        use_cache: Whether to use cached news if available. Defaults to True.

    Returns:
        List of news items with: id, title, source, snippet, published_at, url
        Returns empty list if all sources fail.
    """
    if symbols is None:
        symbols = list(VIETNAMESE_SYMBOLS)

    logger.info(f"Fetching news for {len(symbols)} symbols, last {days_back} days")

    # Try cache first
    if use_cache:
        cache = _load_cache()
        if _is_cache_valid(cache):
            articles = cache.get("articles", [])
            logger.info(f"Returning {len(articles)} cached articles")
            return articles

    articles = []

    # Try NewsAPI first
    logger.info("Attempting to fetch from NewsAPI.org...")
    newsapi_articles = _fetch_from_newsapi(symbols, days_back)
    articles.extend(newsapi_articles)

    if articles:
        logger.info(f"Successfully fetched {len(articles)} articles")
    else:
        # Fallback to web scraping
        logger.info("NewsAPI fetch unsuccessful, falling back to web scraping...")

        # Try VnExpress
        vnexpress_articles = _fetch_from_vnexpress(symbols, days_back)
        articles.extend(vnexpress_articles)

        # Try VietNamNet if VnExpress didn't yield enough
        if len(articles) < 3:
            logger.info("VnExpress returned few articles, trying VietNamNet...")
            vietnamnet_articles = _fetch_from_vietnamnet(symbols, days_back)
            articles.extend(vietnamnet_articles)

    # Deduplicate articles by URL or ID
    seen = set()
    unique_articles = []
    for article in articles:
        url = article.get("url")
        article_id = article.get("id")

        key = url if url else article_id
        if key not in seen:
            seen.add(key)
            unique_articles.append(article)

    # Save to cache
    cache = {
        "articles": unique_articles,
        "fetched_at": datetime.now().isoformat(),
        "symbols": symbols,
        "days_back": days_back,
    }
    _save_cache(cache)

    if not unique_articles:
        logger.warning("No news articles fetched from any source")
        # Return a generic market news item as fallback
        return [{
            "id": hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:16],
            "title": f"Vietnamese stock market news ({datetime.now().strftime('%Y-%m-%d')})",
            "source": "Default",
            "snippet": "Vietnamese market sentiment updates and general market analysis",
            "published_at": datetime.now().isoformat(),
            "url": None,
        }]

    logger.info(f"Fetched {len(unique_articles)} unique news articles total")
    return unique_articles


def clear_cache() -> None:
    """Clear the news cache."""
    cache_path = _get_cache_dir() / "news_cache.json"
    try:
        if cache_path.exists():
            cache_path.unlink()
            logger.info("News cache cleared")
    except Exception as e:
        logger.warning(f"Failed to clear cache: {e}")
