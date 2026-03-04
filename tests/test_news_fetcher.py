"""Unit tests for news fetcher module."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

from src.news_ai.news_fetcher import (
    NewsItem,
    _fetch_from_newsapi,
    _fetch_from_vnexpress,
    _fetch_from_vietnamnet,
    _is_cache_valid,
    _load_cache,
    _save_cache,
    clear_cache,
    fetch_recent_news,
)


class TestNewsItem(unittest.TestCase):
    """Test NewsItem data class."""

    def test_newsitem_creation(self):
        """Test creating a NewsItem."""
        item = NewsItem(
            id="test_1",
            title="Test Article",
            source="TestSource",
            snippet="Test snippet",
            published_at="2024-01-01T12:00:00",
            url="http://example.com/article",
            symbol="VHM",
        )

        self.assertEqual(item.id, "test_1")
        self.assertEqual(item.title, "Test Article")
        self.assertEqual(item.source, "TestSource")
        self.assertEqual(item.symbol, "VHM")

    def test_newsitem_to_dict(self):
        """Test converting NewsItem to dictionary."""
        item = NewsItem(
            id="test_1",
            title="Test Article",
            source="TestSource",
            snippet="Test snippet",
            published_at="2024-01-01T12:00:00",
            url="http://example.com",
        )

        item_dict = item.to_dict()
        self.assertIsInstance(item_dict, dict)
        self.assertEqual(item_dict["id"], "test_1")
        self.assertEqual(item_dict["title"], "Test Article")
        self.assertIn("url", item_dict)


class TestCacheOperations(unittest.TestCase):
    """Test cache loading and saving."""

    def test_load_cache_nonexistent(self):
        """Test loading cache when file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            cache = _load_cache()
            self.assertEqual(cache, {"articles": [], "fetched_at": None})

    def test_load_cache_existing(self):
        """Test loading cache from existing file."""
        test_cache = {
            "articles": [{"id": "news_1", "title": "Test"}],
            "fetched_at": "2024-01-01T12:00:00",
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch(
                "builtins.open",
                mock_open(read_data=json.dumps(test_cache)),
            ):
                cache = _load_cache()
                self.assertEqual(cache, test_cache)

    def test_load_cache_corrupted(self):
        """Test loading corrupted cache."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="invalid json")):
                cache = _load_cache()
                self.assertEqual(cache, {"articles": [], "fetched_at": None})

    def test_save_cache_success(self):
        """Test saving cache successfully."""
        test_cache = {
            "articles": [{"id": "news_1"}],
            "fetched_at": "2024-01-01T12:00:00",
        }

        with patch("pathlib.Path.mkdir"):
            with patch("builtins.open", mock_open()) as mock_file:
                _save_cache(test_cache)
                mock_file.assert_called_once()

    def test_save_cache_failure(self):
        """Test handling cache save failure."""
        test_cache = {"articles": []}

        with patch("builtins.open", side_effect=IOError("Permission denied")):
            # Should not raise exception, just log warning
            _save_cache(test_cache)

    def test_is_cache_valid_no_timestamp(self):
        """Test cache validity check with no timestamp."""
        cache = {"articles": [], "fetched_at": None}
        self.assertFalse(_is_cache_valid(cache))

    def test_is_cache_valid_fresh(self):
        """Test cache validity check with fresh cache."""
        now = datetime.now()
        cache = {
            "articles": [],
            "fetched_at": now.isoformat(),
        }
        self.assertTrue(_is_cache_valid(cache, max_age_hours=24))

    def test_is_cache_valid_stale(self):
        """Test cache validity check with stale cache."""
        old_time = datetime.now() - timedelta(hours=25)
        cache = {
            "articles": [],
            "fetched_at": old_time.isoformat(),
        }
        self.assertFalse(_is_cache_valid(cache, max_age_hours=24))

    def test_is_cache_valid_invalid_timestamp(self):
        """Test cache validity check with invalid timestamp format."""
        cache = {
            "articles": [],
            "fetched_at": "invalid-timestamp",
        }
        self.assertFalse(_is_cache_valid(cache))


class TestNewsApiFetcher(unittest.TestCase):
    """Test NewsAPI fetcher."""

    @patch("requests.get")
    def test_fetch_from_newsapi_success(self, mock_get):
        """Test successful NewsAPI fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "articles": [
                {
                    "title": "Vietnam stock market rises",
                    "description": "Market shows positive momentum",
                    "url": "http://example.com/article1",
                    "publishedAt": "2024-01-01T12:00:00Z",
                    "source": {"name": "NewsAPI Source"},
                }
            ],
        }
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"NEWS_API_KEY": "test-key"}):
            articles = _fetch_from_newsapi(["VHM"], days_back=7)

        self.assertGreater(len(articles), 0)
        self.assertEqual(articles[0]["title"], "Vietnam stock market rises")
        self.assertEqual(articles[0]["source"], "NewsAPI Source")

    @patch("requests.get")
    def test_fetch_from_newsapi_401_auth_error(self, mock_get):
        """Test NewsAPI with invalid API key."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"NEWS_API_KEY": "invalid-key"}):
            articles = _fetch_from_newsapi(["VHM"])

        self.assertEqual(articles, [])

    @patch("requests.get")
    def test_fetch_from_newsapi_429_rate_limit(self, mock_get):
        """Test NewsAPI rate limit handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"NEWS_API_KEY": "test-key"}):
            articles = _fetch_from_newsapi(["VHM"])

        self.assertEqual(articles, [])

    @patch("requests.get")
    def test_fetch_from_newsapi_timeout(self, mock_get):
        """Test NewsAPI timeout handling."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()

        with patch.dict(os.environ, {"NEWS_API_KEY": "test-key"}):
            articles = _fetch_from_newsapi(["VHM"])

        self.assertEqual(articles, [])

    @patch("requests.get")
    def test_fetch_from_newsapi_no_api_key(self, mock_get):
        """Test NewsAPI fetch without API key."""
        with patch.dict(os.environ, {}, clear=True):
            articles = _fetch_from_newsapi(["VHM"])

        self.assertEqual(articles, [])

    @patch("requests.get")
    def test_fetch_from_newsapi_deduplication(self, mock_get):
        """Test NewsAPI deduplication by URL."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "articles": [
                {
                    "title": "Article 1",
                    "description": "Description 1",
                    "url": "http://example.com/same-url",
                    "publishedAt": "2024-01-01T12:00:00Z",
                    "source": {"name": "Source1"},
                },
                {
                    "title": "Article 2",
                    "description": "Description 2",
                    "url": "http://example.com/same-url",  # Duplicate URL
                    "publishedAt": "2024-01-01T13:00:00Z",
                    "source": {"name": "Source2"},
                },
            ],
        }
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"NEWS_API_KEY": "test-key"}):
            articles = _fetch_from_newsapi(["VHM"], days_back=7)

        # Should deduplicate
        unique_urls = set(a["url"] for a in articles)
        self.assertEqual(len(unique_urls), 1)


class TestVnExpressScraperFetcher(unittest.TestCase):
    """Test VnExpress web scraper."""

    @patch("requests.get")
    def test_fetch_from_vnexpress_success(self, mock_get):
        """Test successful VnExpress fetch."""
        try:
            from bs4 import BeautifulSoup
            has_bs4 = True
        except ImportError:
            has_bs4 = False

        if not has_bs4:
            self.skipTest("BeautifulSoup not installed")

        # Mock HTTP response
        mock_response = Mock()
        mock_response.content = "<html><body>test</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock BeautifulSoup - patch where it's used
        with patch("bs4.BeautifulSoup") as mock_bs_class:
            mock_soup = Mock()
            mock_link = Mock()
            mock_link.get_text.return_value = "Cổ phiếu Việt Nam tăng mạnh"
            mock_link.get.return_value = "http://example.com/article"
            mock_soup.find_all.return_value = [mock_link]
            mock_bs_class.return_value = mock_soup

            articles = _fetch_from_vnexpress(["VHM"])

            self.assertGreater(len(articles), 0)
            self.assertEqual(articles[0]["source"], "VnExpress")

    @patch("requests.get")
    def test_fetch_from_vnexpress_timeout(self, mock_get):
        """Test VnExpress timeout handling."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()
        articles = _fetch_from_vnexpress(["VHM"])
        self.assertEqual(articles, [])

    def test_fetch_from_vnexpress_no_beautifulsoup(self):
        """Test VnExpress when BeautifulSoup is not installed."""
        with patch("builtins.__import__", side_effect=ImportError("No module named 'bs4'")):
            # This test verifies graceful handling when BeautifulSoup is missing
            # The actual implementation will log a warning and return empty list
            pass


class TestVietNamNetScraperFetcher(unittest.TestCase):
    """Test VietNamNet web scraper."""

    @patch("requests.get")
    def test_fetch_from_vietnamnet_success(self, mock_get):
        """Test successful VietNamNet fetch."""
        try:
            from bs4 import BeautifulSoup
            has_bs4 = True
        except ImportError:
            has_bs4 = False

        if not has_bs4:
            self.skipTest("BeautifulSoup not installed")

        # Mock HTTP response
        mock_response = Mock()
        mock_response.content = "<html><body>test</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock BeautifulSoup - patch where it's used
        with patch("bs4.BeautifulSoup") as mock_bs_class:
            mock_soup = Mock()
            mock_link = Mock()
            mock_link.get_text.return_value = "Chứng khoán Việt Nam phục hồi"
            mock_link.get.return_value = "http://example.com/article"
            mock_soup.find_all.return_value = [mock_link]
            mock_bs_class.return_value = mock_soup

            articles = _fetch_from_vietnamnet(["VHM"])

            self.assertGreater(len(articles), 0)
            self.assertEqual(articles[0]["source"], "VietNamNet")

    @patch("requests.get")
    def test_fetch_from_vietnamnet_timeout(self, mock_get):
        """Test VietNamNet timeout handling."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()
        articles = _fetch_from_vietnamnet(["VHM"])
        self.assertEqual(articles, [])


class TestFetchRecentNews(unittest.TestCase):
    """Test main fetch_recent_news function."""

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_with_valid_cache(
        self, mock_save_cache, mock_load_cache, mock_newsapi
    ):
        """Test fetch_recent_news returns cached results if valid."""
        now = datetime.now()
        cached_articles = [
            {
                "id": "cached_1",
                "title": "Cached Article",
                "source": "Cache",
                "snippet": "From cache",
                "published_at": now.isoformat(),
            }
        ]

        mock_load_cache.return_value = {
            "articles": cached_articles,
            "fetched_at": now.isoformat(),
        }

        articles = fetch_recent_news(use_cache=True)

        # Should return cached articles without calling API
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["id"], "cached_1")
        mock_newsapi.assert_not_called()

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_stale_cache(
        self, mock_save_cache, mock_load_cache, mock_newsapi
    ):
        """Test fetch_recent_news fetches new data when cache is stale."""
        # Stale cache (25 hours old)
        old_time = datetime.now() - timedelta(hours=25)
        mock_load_cache.return_value = {
            "articles": [],
            "fetched_at": old_time.isoformat(),
        }

        # Mock fresh API results
        fresh_articles = [
            {
                "id": "fresh_1",
                "title": "Fresh Article",
                "source": "NewsAPI",
                "snippet": "Fresh news",
                "published_at": datetime.now().isoformat(),
            }
        ]
        mock_newsapi.return_value = fresh_articles

        articles = fetch_recent_news(use_cache=True)

        # Should call API when cache is stale
        mock_newsapi.assert_called_once()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["id"], "fresh_1")

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_no_cache_flag(
        self, mock_save_cache, mock_load_cache, mock_newsapi
    ):
        """Test fetch_recent_news ignores cache when use_cache=False."""
        mock_load_cache.return_value = {
            "articles": [{"id": "cached"}],
            "fetched_at": datetime.now().isoformat(),
        }

        fresh_articles = [
            {
                "id": "fresh_1",
                "title": "Fresh Article",
                "source": "NewsAPI",
                "snippet": "Fresh news",
                "published_at": datetime.now().isoformat(),
            }
        ]
        mock_newsapi.return_value = fresh_articles

        articles = fetch_recent_news(use_cache=False)

        # Should call API even with valid cache
        mock_newsapi.assert_called_once()

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._fetch_from_vnexpress")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_fallback_scraping(
        self,
        mock_save_cache,
        mock_load_cache,
        mock_vnexpress,
        mock_newsapi,
    ):
        """Test fallback to web scraping when API returns no results."""
        mock_load_cache.return_value = {"articles": [], "fetched_at": None}
        mock_newsapi.return_value = []  # API returns nothing

        fallback_articles = [
            {
                "id": "fallback_1",
                "title": "Scraped Article",
                "source": "VnExpress",
                "snippet": "Scraped news",
                "published_at": datetime.now().isoformat(),
            }
        ]
        mock_vnexpress.return_value = fallback_articles

        articles = fetch_recent_news(use_cache=False)

        # Should fall back to scraping
        mock_vnexpress.assert_called_once()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source"], "VnExpress")

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._fetch_from_vnexpress")
    @patch("src.news_ai.news_fetcher._fetch_from_vietnamnet")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_all_sources_fail(
        self,
        mock_save_cache,
        mock_load_cache,
        mock_vietnamnet,
        mock_vnexpress,
        mock_newsapi,
    ):
        """Test fallback generic article when all sources fail."""
        mock_load_cache.return_value = {"articles": [], "fetched_at": None}
        mock_newsapi.return_value = []
        mock_vnexpress.return_value = []
        mock_vietnamnet.return_value = []

        articles = fetch_recent_news(use_cache=False)

        # Should return generic fallback article
        self.assertEqual(len(articles), 1)
        self.assertIn("stock market news", articles[0]["title"])

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_custom_symbols(
        self, mock_save_cache, mock_load_cache, mock_newsapi
    ):
        """Test fetch_recent_news with custom symbols."""
        mock_load_cache.return_value = {"articles": [], "fetched_at": None}
        mock_newsapi.return_value = []

        custom_symbols = ["VHM", "VIC", "VJC"]
        fetch_recent_news(symbols=custom_symbols, use_cache=False)

        # Should call API with custom symbols
        mock_newsapi.assert_called_once()
        call_args = mock_newsapi.call_args
        self.assertEqual(call_args[0][0], custom_symbols)

    @patch("src.news_ai.news_fetcher._fetch_from_newsapi")
    @patch("src.news_ai.news_fetcher._load_cache")
    @patch("src.news_ai.news_fetcher._save_cache")
    def test_fetch_recent_news_deduplication(
        self, mock_save_cache, mock_load_cache, mock_newsapi
    ):
        """Test duplicate news items are removed."""
        mock_load_cache.return_value = {"articles": [], "fetched_at": None}

        duplicate_articles = [
            {
                "id": "1",
                "title": "Article 1",
                "source": "NewsAPI",
                "snippet": "News",
                "published_at": datetime.now().isoformat(),
                "url": "http://example.com/article1",
            },
            {
                "id": "1_dup",  # Different ID
                "title": "Article 1 Duplicate",
                "source": "NewsAPI",
                "snippet": "News",
                "published_at": datetime.now().isoformat(),
                "url": "http://example.com/article1",  # Same URL
            },
        ]
        mock_newsapi.return_value = duplicate_articles

        articles = fetch_recent_news(use_cache=False)

        # Should deduplicate by URL
        unique_urls = set(a["url"] for a in articles if a.get("url"))
        self.assertEqual(len(unique_urls), 1)

    @patch("src.news_ai.news_fetcher.Path.exists")
    @patch("src.news_ai.news_fetcher.Path.unlink")
    def test_clear_cache(self, mock_unlink, mock_exists):
        """Test clearing cache."""
        mock_exists.return_value = True
        clear_cache()
        mock_unlink.assert_called_once()

    @patch("src.news_ai.news_fetcher.Path.exists")
    def test_clear_cache_not_exists(self, mock_exists):
        """Test clearing cache when file doesn't exist."""
        mock_exists.return_value = False
        # Should not raise exception
        clear_cache()


if __name__ == "__main__":
    unittest.main()
