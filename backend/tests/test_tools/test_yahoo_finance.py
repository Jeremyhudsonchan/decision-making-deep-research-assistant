"""
Tests for the Yahoo Finance tool wrapper.
All tests mock yf.Ticker to avoid real network calls.
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_ticker_info(**kwargs) -> dict:
    """Build a minimal yfinance info dict with sensible defaults."""
    defaults = {
        "longName": "Apple Inc.",
        "shortName": "Apple",
        "currentPrice": 182.50,
        "regularMarketPrice": 182.50,
        "previousClose": 180.00,
        "marketCap": 2_800_000_000_000,
        "currency": "USD",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "country": "United States",
        "website": "https://apple.com",
        "fullTimeEmployees": 164_000,
        "longBusinessSummary": "Apple Inc. designs and sells consumer electronics.",
        "totalRevenue": 383_000_000_000,
        "grossProfits": 170_000_000_000,
        "netIncomeToCommon": 97_000_000_000,
        "profitMargins": 0.2531,
        "revenueGrowth": 0.02,
        "earningsGrowth": 0.10,
        "freeCashflow": 90_000_000_000,
        "debtToEquity": 150.0,
        "ebitda": 125_000_000_000,
        "trailingPE": 28.5,
        "trailingEps": 6.40,
        "dividendYield": 0.0054,
        "fiftyTwoWeekHigh": 199.62,
        "fiftyTwoWeekLow": 143.90,
    }
    defaults.update(kwargs)
    return defaults


def _mock_ticker(info_dict: dict):
    """Patch yf.Ticker to return a mock with the given .info dict."""
    mock_ticker = MagicMock()
    mock_ticker.info = info_dict
    return mock_ticker


class TestExtractTicker:
    def test_dollar_sign_prefix(self):
        from app.agent.tools.yahoo_finance import _extract_ticker

        assert _extract_ticker("What is $AAPL trading at?") == "AAPL"

    def test_parenthesis_suffix(self):
        from app.agent.tools.yahoo_finance import _extract_ticker

        assert _extract_ticker("Apple (AAPL) earnings") == "AAPL"

    def test_parenthesis_wrap(self):
        from app.agent.tools.yahoo_finance import _extract_ticker

        assert _extract_ticker("(AAPL) stock analysis") == "AAPL"

    def test_fallback_uppercase_word(self):
        from app.agent.tools.yahoo_finance import _extract_ticker

        assert _extract_ticker("TSLA revenue last quarter") == "TSLA"

    def test_no_match_returns_none(self):
        from app.agent.tools.yahoo_finance import _extract_ticker

        # All words are >5 chars so the fallback finds no 1-5 char uppercase word
        assert _extract_ticker("analyzing modern technology performance benchmarks") is None


class TestGetStockPrice:
    def test_formats_price_output(self):
        from app.agent.tools.yahoo_finance import get_stock_price

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = get_stock_price("AAPL")

        assert "Apple Inc." in result
        assert "182.5" in result
        assert "USD" in result

    def test_handles_missing_price_gracefully(self):
        from app.agent.tools.yahoo_finance import get_stock_price

        info = _make_ticker_info(currentPrice=None, regularMarketPrice=None)
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = get_stock_price("AAPL")

        assert "Price: N/A" in result

    def test_yfinance_exception_returns_error_string(self):
        from app.agent.tools.yahoo_finance import get_stock_price

        with patch("yfinance.Ticker", side_effect=Exception("Network error")):
            result = get_stock_price("AAPL")

        assert "Failed to get stock price" in result


class TestGetCompanyInfo:
    def test_includes_sector_and_industry(self):
        from app.agent.tools.yahoo_finance import get_company_info

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = get_company_info("AAPL")

        assert "Technology" in result
        assert "Consumer Electronics" in result

    def test_includes_business_summary(self):
        from app.agent.tools.yahoo_finance import get_company_info

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = get_company_info("AAPL")

        assert "Apple Inc. designs and sells consumer electronics." in result


class TestGetFinancials:
    def test_includes_revenue_and_margin(self):
        from app.agent.tools.yahoo_finance import get_financials

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = get_financials("AAPL")

        assert "383.00B" in result  # totalRevenue formatted
        assert "25.31%" in result   # profitMargins formatted

    def test_handles_missing_financials_gracefully(self):
        from app.agent.tools.yahoo_finance import get_financials

        info = _make_ticker_info(
            totalRevenue=None,
            grossProfits=None,
            netIncomeToCommon=None,
            profitMargins=None,
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = get_financials("AAPL")

        # Should still return something (ticker header line)
        assert "AAPL" in result


class TestFinanceSearch:
    def test_routes_to_company_info_for_broad_question(self):
        from app.agent.tools.yahoo_finance import finance_search

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = finance_search("Tell me about $AAPL company and sector")

        # Company info keywords should appear
        assert "Technology" in result

    def test_routes_to_financials_for_financial_question(self):
        from app.agent.tools.yahoo_finance import finance_search

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = finance_search("What is AAPL revenue and profit margin?")

        # Financial data should appear
        assert "383.00B" in result

    def test_always_includes_stock_price(self):
        from app.agent.tools.yahoo_finance import finance_search

        info = _make_ticker_info()
        with patch("yfinance.Ticker", return_value=_mock_ticker(info)):
            result = finance_search("$AAPL stock info")

        assert "182.5" in result

    def test_no_ticker_returns_informative_string(self):
        from app.agent.tools.yahoo_finance import finance_search

        # All words are >5 chars so no ticker is extracted
        result = finance_search("analyzing modern technology performance benchmarks")

        assert result != ""
        assert "Could not extract" in result or "ticker" in result.lower()
