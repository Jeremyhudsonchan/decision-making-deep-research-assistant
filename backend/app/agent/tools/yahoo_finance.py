"""
Yahoo Finance tool using yfinance.
Provides stock price, company info, and financial summaries.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_stock_price(ticker: str) -> str:
    """Get current stock price and basic market data for a ticker."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose")
        market_cap = info.get("marketCap")
        currency = info.get("currency", "USD")
        name = info.get("longName") or info.get("shortName", ticker)

        change = None
        change_pct = None
        if price and prev_close:
            change = round(price - prev_close, 4)
            change_pct = round((change / prev_close) * 100, 2)

        lines = [
            f"Stock: {name} ({ticker.upper()})",
            f"Current Price: {price} {currency}" if price else "Price: N/A",
            f"Change: {change:+.4f} ({change_pct:+.2f}%)" if change is not None else "",
            f"Previous Close: {prev_close}" if prev_close else "",
            f"Market Cap: {_format_large_number(market_cap)}" if market_cap else "",
        ]
        return "\n".join(l for l in lines if l)

    except Exception as e:
        logger.error(f"get_stock_price failed for {ticker}: {e}")
        return f"Failed to get stock price for {ticker}: {str(e)}"


def get_company_info(ticker: str) -> str:
    """Get company description, sector, industry, and key metrics."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        name = info.get("longName") or info.get("shortName", ticker)
        summary = info.get("longBusinessSummary", "No description available.")[:1000]
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        employees = info.get("fullTimeEmployees")
        website = info.get("website", "N/A")
        country = info.get("country", "N/A")

        pe_ratio = info.get("trailingPE")
        eps = info.get("trailingEps")
        div_yield = info.get("dividendYield")
        week_52_high = info.get("fiftyTwoWeekHigh")
        week_52_low = info.get("fiftyTwoWeekLow")

        lines = [
            f"Company: {name} ({ticker.upper()})",
            f"Sector: {sector} | Industry: {industry}",
            f"Country: {country} | Website: {website}",
            f"Employees: {employees:,}" if employees else "",
            f"P/E Ratio: {pe_ratio:.2f}" if pe_ratio else "",
            f"EPS (TTM): {eps}" if eps else "",
            f"Dividend Yield: {div_yield:.2%}" if div_yield else "",
            f"52-Week Range: {week_52_low} - {week_52_high}" if week_52_high else "",
            f"\nDescription: {summary}",
        ]
        return "\n".join(l for l in lines if l)

    except Exception as e:
        logger.error(f"get_company_info failed for {ticker}: {e}")
        return f"Failed to get company info for {ticker}: {str(e)}"


def get_financials(ticker: str) -> str:
    """Get recent income statement highlights."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        name = info.get("longName") or info.get("shortName", ticker)
        revenue = info.get("totalRevenue")
        gross_profit = info.get("grossProfits")
        ebitda = info.get("ebitda")
        net_income = info.get("netIncomeToCommon")
        profit_margin = info.get("profitMargins")
        revenue_growth = info.get("revenueGrowth")
        earnings_growth = info.get("earningsGrowth")
        free_cash_flow = info.get("freeCashflow")
        debt_to_equity = info.get("debtToEquity")

        lines = [
            f"Financials: {name} ({ticker.upper()})",
            f"Total Revenue: {_format_large_number(revenue)}" if revenue else "",
            f"Gross Profit: {_format_large_number(gross_profit)}" if gross_profit else "",
            f"EBITDA: {_format_large_number(ebitda)}" if ebitda else "",
            f"Net Income: {_format_large_number(net_income)}" if net_income else "",
            f"Profit Margin: {profit_margin:.2%}" if profit_margin else "",
            f"Revenue Growth (YoY): {revenue_growth:.2%}" if revenue_growth else "",
            f"Earnings Growth (YoY): {earnings_growth:.2%}" if earnings_growth else "",
            f"Free Cash Flow: {_format_large_number(free_cash_flow)}" if free_cash_flow else "",
            f"Debt/Equity: {debt_to_equity:.2f}" if debt_to_equity else "",
        ]
        return "\n".join(l for l in lines if l)

    except Exception as e:
        logger.error(f"get_financials failed for {ticker}: {e}")
        return f"Failed to get financials for {ticker}: {str(e)}"


def finance_search(query: str) -> str:
    """
    Interpret a natural language finance query, extract ticker(s), and return relevant data.
    This is the main entry point called by the research node.
    """
    ticker = _extract_ticker(query)
    if not ticker:
        return f"Could not extract a stock ticker from query: '{query}'. Please specify a ticker symbol."

    query_lower = query.lower()
    parts = []

    # Always include price
    parts.append(get_stock_price(ticker))

    # Include company info for broad questions
    if any(w in query_lower for w in ["about", "what is", "company", "business", "analyst", "sector", "industry"]):
        parts.append("\n" + get_company_info(ticker))

    # Include financials for financial questions
    if any(w in query_lower for w in ["revenue", "profit", "earning", "financial", "income", "cash flow", "debt", "margin"]):
        parts.append("\n" + get_financials(ticker))

    return "\n".join(parts)


def _extract_ticker(text: str) -> Optional[str]:
    """Heuristic: find an all-caps word that looks like a ticker (1-5 chars)."""
    import re
    # Look for explicit ticker patterns like (AAPL) or $AAPL
    patterns = [
        r'\$([A-Z]{1,5})\b',           # $AAPL
        r'\b([A-Z]{1,5})\b(?=\s*\))',  # AAPL)
        r'\(([A-Z]{1,5})\)',            # (AAPL)
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    # Fallback: find any uppercase word 1-5 chars (crude)
    words = text.split()
    for word in words:
        cleaned = re.sub(r'[^A-Z]', '', word.upper())
        if 1 <= len(cleaned) <= 5:
            common_words = {"I", "A", "THE", "AND", "OR", "FOR", "OF", "IN", "IS", "IT", "BE"}
            if cleaned not in common_words:
                return cleaned
    return None


def _format_large_number(n) -> str:
    if n is None:
        return "N/A"
    try:
        n = float(n)
        if abs(n) >= 1e12:
            return f"${n/1e12:.2f}T"
        elif abs(n) >= 1e9:
            return f"${n/1e9:.2f}B"
        elif abs(n) >= 1e6:
            return f"${n/1e6:.2f}M"
        else:
            return f"${n:,.0f}"
    except (TypeError, ValueError):
        return str(n)
