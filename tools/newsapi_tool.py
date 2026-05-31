import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_BASE = "https://newsapi.org/v2"
TIMEOUT = 15

POSITIVE_WORDS = {
    "growth", "growing", "raise", "raised", "funding", "funded", "launch",
    "launched", "expand", "expanding", "innovative", "breakthrough", "record",
    "profit", "profitable", "success", "successful", "win", "winning", "wins",
    "strong", "surge", "soar", "soared", "boost", "boosted", "rise", "rising",
    "jump", "jumped", "rally", "beat", "beats", "exceed", "exceeded", "milestone",
    "partnership", "acquire", "acquired", "acquisition", "ipo", "unicorn",
    "leading", "leader", "best", "top", "approval", "approved", "patent",
    "award", "awarded", "secured", "deal",
}

NEGATIVE_WORDS = {
    "loss", "losses", "layoff", "layoffs", "fired", "shutdown", "closing",
    "closed", "decline", "declining", "drop", "dropped", "fall", "fell",
    "plunge", "plunged", "crash", "crashed", "fraud", "scandal", "lawsuit",
    "sue", "sued", "investigation", "fine", "fined", "penalty", "violation",
    "breach", "hack", "hacked", "leak", "leaked", "controversy", "criticism",
    "criticized", "fail", "failed", "failure", "bankrupt", "bankruptcy",
    "weak", "weakness", "concern", "concerns", "risk", "risky", "warning",
    "warn", "warned", "slump", "downturn", "miss", "missed", "delay",
    "delayed", "recall", "outage",
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on", "at",
    "by", "with", "as", "is", "it", "its", "be", "this", "that", "from",
    "are", "was", "were", "has", "have", "had", "will", "would", "can",
    "could", "should", "may", "might", "must", "do", "does", "did", "not",
    "no", "yes", "if", "then", "than", "so", "such", "into", "about", "over",
    "after", "before", "between", "through", "during", "out", "up", "down",
    "more", "most", "some", "any", "all", "each", "every", "other",
    "another", "new", "year", "years", "day", "days", "week", "month",
    "company", "companies", "said", "says", "say",
}


def _empty_result() -> dict:
    return {
        "total_articles": 0,
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "sentiment_score": 0.0,
        "top_articles": [],
        "key_themes": [],
    }


def _classify_sentiment(text: str) -> tuple[str, int, int]:
    if not text:
        return "neutral", 0, 0
    words = re.findall(r"[a-zA-Z]+", text.lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    if pos > neg:
        return "positive", pos, neg
    if neg > pos:
        return "negative", pos, neg
    return "neutral", pos, neg


def _extract_themes(texts: list[str], top_n: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for t in texts:
        if not t:
            continue
        for w in re.findall(r"[a-zA-Z]{4,}", t.lower()):
            if w in STOP_WORDS:
                continue
            counter[w] += 1
    return [w for w, _ in counter.most_common(top_n)]


def fetch_news_data(company_name: str) -> dict:
    if not company_name or not NEWSAPI_KEY:
        return _empty_result()

    from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    try:
        r = requests.get(
            f"{NEWSAPI_BASE}/everything",
            params={
                "q": f'"{company_name}"',
                "from": from_date,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": 100,
                "apiKey": NEWSAPI_KEY,
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return _empty_result()
        payload = r.json() or {}
        articles = payload.get("articles", []) or []
    except Exception:
        return _empty_result()

    if not articles:
        return _empty_result()

    pos = neg = neu = 0
    enriched: list[dict] = []
    theme_corpus: list[str] = []

    for art in articles:
        title = art.get("title") or ""
        desc = art.get("description") or ""
        text = f"{title}. {desc}"
        sentiment, _p, _n = _classify_sentiment(text)
        if sentiment == "positive":
            pos += 1
        elif sentiment == "negative":
            neg += 1
        else:
            neu += 1

        theme_corpus.append(text)

        enriched.append(
            {
                "title": title,
                "source": ((art.get("source") or {}).get("name")) or "",
                "url": art.get("url") or "",
                "sentiment": sentiment,
                "date": art.get("publishedAt") or "",
            }
        )

    total = len(articles)
    sentiment_score = round((pos - neg) / total, 3) if total else 0.0

    enriched.sort(key=lambda x: x.get("date") or "", reverse=True)
    top_articles = enriched[:15]

    return {
        "total_articles": total,
        "positive_count": pos,
        "negative_count": neg,
        "neutral_count": neu,
        "sentiment_score": sentiment_score,
        "top_articles": top_articles,
        "key_themes": _extract_themes(theme_corpus),
    }
