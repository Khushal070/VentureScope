import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

PYTRENDS_HL = os.getenv("PYTRENDS_HL", "en-US")
PYTRENDS_TZ = int(os.getenv("PYTRENDS_TZ", "360"))

# Generic suffixes that dilute a Google Trends query (e.g. "Perplexity AI").
_GENERIC_TOKENS = {
    "ai", "inc", "inc.", "llc", "ltd", "ltd.", "corp", "corp.", "co", "co.",
    "labs", "lab", "technologies", "technology", "tech", "software", "systems",
    "app", "io", "the", "company", "group", "global", "solutions",
}


def _trend_term(company_name: str) -> str:
    """Reduce a company name to a cleaner Google Trends query.

    Strips trailing generic tokens so "Perplexity AI" -> "Perplexity", while
    leaving single-token brands (e.g. "OpenAI", "Stripe") untouched.
    """
    tokens = company_name.strip().split()
    if len(tokens) <= 1:
        return company_name.strip()
    kept = [t for t in tokens if t.lower().strip(".,") not in _GENERIC_TOKENS]
    if not kept:
        kept = tokens[:1]
    return " ".join(kept)


def _empty_result() -> dict:
    return {
        "current_interest": 0,
        "trend_direction": "stable",
        "peak_interest": 0,
        "avg_interest": 0,
        "monthly_data": [],
    }


def _direction(first_half_avg: float, second_half_avg: float) -> str:
    if second_half_avg == 0 and first_half_avg == 0:
        return "stable"
    if first_half_avg == 0:
        return "rising"
    delta_pct = (second_half_avg - first_half_avg) / max(first_half_avg, 1.0)
    if delta_pct > 0.15:
        return "rising"
    if delta_pct < -0.15:
        return "falling"
    return "stable"


def fetch_trends_data(company_name: str) -> dict:
    if not company_name:
        return _empty_result()

    term = _trend_term(company_name)

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl=PYTRENDS_HL, tz=PYTRENDS_TZ, timeout=(10, 25))
        pytrends.build_payload(
            kw_list=[term],
            cat=0,
            timeframe="today 12-m",
            geo="",
            gprop="",
        )
        df = pytrends.interest_over_time()
    except Exception:
        return _empty_result()

    if df is None or df.empty or term not in df.columns:
        return _empty_result()

    series = df[term]
    values = [int(v) for v in series.tolist()]
    if not values:
        return _empty_result()

    monthly_data: list[dict] = []
    for ts, v in zip(series.index, values):
        try:
            label = ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else str(ts)
        except Exception:
            label = str(ts)
        monthly_data.append({"date": label, "interest": int(v)})

    half = max(1, len(values) // 2)
    first_avg = sum(values[:half]) / half
    second_avg = sum(values[half:]) / max(1, len(values) - half)

    return {
        "current_interest": int(values[-1]),
        "trend_direction": _direction(first_avg, second_avg),
        "peak_interest": int(max(values)),
        "avg_interest": int(round(sum(values) / len(values))),
        "monthly_data": monthly_data,
    }
