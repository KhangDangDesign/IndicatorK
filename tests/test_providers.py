"""Tests for provider selection from config and composite fallback."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.models import OHLCV
from src.providers.base import PriceProvider
from src.providers.cache_provider import CacheProvider
from src.providers.composite_provider import CompositeProvider


class MockProvider(PriceProvider):
    """Mock provider for testing."""

    def __init__(self, name="mock", prices=None, history=None, should_fail=False):
        self.name = name
        self._prices = prices or {}
        self._history = history or []
        self._should_fail = should_fail

    def get_last_prices(self, symbols):
        if self._should_fail:
            raise RuntimeError("Mock provider failed")
        return {s: self._prices[s] for s in symbols if s in self._prices}

    def get_daily_history(self, symbol, start, end):
        if self._should_fail:
            raise RuntimeError("Mock provider failed")
        return self._history


class TestCompositeProvider:
    def test_primary_success(self):
        primary = MockProvider("primary", prices={"HPG": 25000})
        secondary = MockProvider("secondary", prices={"HPG": 24000})
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        result = composite.get_last_prices(["HPG"])
        assert result["HPG"] == 25000

    def test_fallback_to_secondary(self):
        primary = MockProvider("primary", should_fail=True)
        secondary = MockProvider("secondary", prices={"HPG": 24000})
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        result = composite.get_last_prices(["HPG"])
        assert result["HPG"] == 24000

    def test_fallback_to_cache(self):
        primary = MockProvider("primary", should_fail=True)
        secondary = MockProvider("secondary", should_fail=True)
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {"HPG": {"last_price": 23000, "updated_at": "2025-01-01"}}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        result = composite.get_last_prices(["HPG"])
        assert result["HPG"] == 23000

    def test_all_fail_empty_result(self):
        primary = MockProvider("primary", should_fail=True)
        secondary = MockProvider("secondary", should_fail=True)
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        result = composite.get_last_prices(["HPG"])
        assert result == {}

    def test_partial_fill_from_secondary(self):
        primary = MockProvider("primary", prices={"HPG": 25000})
        secondary = MockProvider("secondary", prices={"HPG": 24000, "VNM": 80000})
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        result = composite.get_last_prices(["HPG", "VNM"])
        assert result["HPG"] == 25000
        assert result["VNM"] == 80000

    def test_health_stats(self):
        primary = MockProvider("primary", should_fail=True)
        secondary = MockProvider("secondary", prices={"HPG": 24000})
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        composite.get_last_prices(["HPG"])
        health = composite.get_health_stats()
        assert health.total_errors >= 1
        assert health.name == "primary->secondary->cache"

    def test_history_fallback(self):
        sample = [
            OHLCV(date(2025, 1, 1), 100, 110, 95, 105, 1000),
            OHLCV(date(2025, 1, 2), 105, 115, 100, 110, 1200),
        ]
        primary = MockProvider("primary", should_fail=True)
        secondary = MockProvider("secondary", history=sample)
        cache = CacheProvider.__new__(CacheProvider)
        cache._data = {}
        cache.cache_path = "/dev/null"

        composite = CompositeProvider(primary, secondary, cache)
        result = composite.get_daily_history("HPG", date(2025, 1, 1), date(2025, 1, 2))
        assert len(result) == 2


class TestConfigDrivenSelection:
    def test_provider_from_config(self, tmp_path):
        config = tmp_path / "providers.yml"
        config.write_text(
            "primary: cache\n"
            "secondary: cache\n"
            "cache_path: " + str(tmp_path / "cache.json") + "\n"
        )
        (tmp_path / "cache.json").write_text("{}")

        from src.utils.config import get_provider
        provider = get_provider(str(config))
        assert provider.name == "composite"

    def test_invalid_provider_name(self, tmp_path):
        config = tmp_path / "providers.yml"
        config.write_text("primary: nonexistent\nsecondary: cache\ncache_path: /tmp/c.json\n")

        from src.utils.config import get_provider
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider(str(config))

    def test_provider_falls_back_when_primary_init_fails(self, tmp_path, monkeypatch):
        config = tmp_path / "providers.yml"
        cache_path = tmp_path / "cache.json"
        config.write_text(
            "primary: vnstock\n"
            "secondary: cache\n"
            "cache_path: " + str(cache_path) + "\n"
        )
        cache_path.write_text('{"HPG": {"last_price": 23.0, "updated_at": "2025-01-01"}}')

        from src.providers.vnstock_provider import VnstockProvider
        from src.utils.config import get_provider

        def fail_init(self, source="VCI", timeout=30):
            raise ImportError("vnstock missing transitive dependency")

        monkeypatch.setattr(VnstockProvider, "__init__", fail_init)

        provider = get_provider(str(config))

        assert provider.get_last_prices(["HPG"]) == {"HPG": 23.0}


class TestVnstockProvider:
    def test_legacy_prices_are_normalized_to_thousands(self):
        from src.providers.vnstock_provider import VnstockProvider

        class FakeDataFrame:
            columns = ["time", "open", "high", "low", "close", "volume"]

            def iterrows(self):
                yield 0, {
                    "time": "2025-03-03",
                    "open": 20800,
                    "high": 21100,
                    "low": 20700,
                    "close": 20860,
                    "volume": 1000000,
                }

        provider = VnstockProvider.__new__(VnstockProvider)
        records = provider._parse_dataframe(FakeDataFrame())

        assert records[0].open == 20.8
        assert records[0].high == 21.1
        assert records[0].low == 20.7
        assert records[0].close == 20.86
