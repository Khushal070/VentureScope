import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

# The legacy PatentsView endpoint (api.patentsview.org/patents/query) was retired
# in 2025 and now returns HTML. We use Google Patents' keyless XHR search instead.
GOOGLE_PATENTS_XHR = "https://patents.google.com/xhr/query"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 20


def _empty_result() -> dict:
    return {
        "total_patents": 0,
        "recent_patents": [],
        "patent_velocity": 0,
        "ip_score": 0.0,
    }


_GENERIC_TOKENS = {
    "ai", "inc", "inc.", "llc", "ltd", "ltd.", "corp", "corp.", "co", "co.",
    "labs", "lab", "technologies", "technology", "tech", "software", "systems",
    "the", "company", "group", "global", "holdings",
}


def _assignee_term(company_name: str) -> str:
    """Reduce a company name to a core assignee keyword for a broad match.

    USPTO assignees are inconsistent ("Perplexity AI, Inc." vs "Perplexity"),
    so we search the core token: "Perplexity AI" -> "Perplexity".
    """
    tokens = company_name.strip().split()
    if len(tokens) <= 1:
        return company_name.strip()
    kept = [t for t in tokens if t.lower().strip(".,") not in _GENERIC_TOKENS]
    return " ".join(kept) if kept else tokens[0]


def _ip_score(total: int, recent_12m: int) -> float:
    """Score patent portfolio 0-10 from volume and recent activity."""
    score = 0.0
    if total > 0:
        score += min(5.0, 1.5 + 1.0 * (total ** 0.5) / 3.0)
    if recent_12m > 0:
        score += min(5.0, 1.0 + recent_12m * 0.4)
    return round(min(score, 10.0), 2)


def fetch_patents_data(company_name: str) -> dict:
    if not company_name:
        return _empty_result()

    term = _assignee_term(company_name)
    # Query Google Patents by assignee. "perplexity" is also an NLP term, so we
    # MUST filter returned rows by the assignee field to drop unrelated patents.
    inner = f'q=assignee:"{term}"&num=50'
    url = f"{GOOGLE_PATENTS_XHR}?" + urllib.parse.urlencode({"url": inner, "exp": ""})

    payload = _gp_get(url)
    if not payload:
        return _empty_result()

    rows: list[dict] = []
    for cluster in ((payload.get("results") or {}).get("cluster") or []):
        for item in cluster.get("result") or []:
            patent = item.get("patent")
            if patent:
                rows.append(patent)

    # Keep only patents whose assignee actually matches the company.
    term_l = term.lower()
    matched = [p for p in rows if term_l in _assignee_str(p.get("assignee")).lower()]

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    recent_patents: list[dict] = []
    velocity = 0

    for p in matched:
        number = p.get("publication_number")
        title = (p.get("title") or "").strip()
        date_str = (
            p.get("grant_date") or p.get("publication_date") or p.get("filing_date") or ""
        )
        pdate = _parse_patent_date(date_str)
        if pdate and pdate >= cutoff:
            velocity += 1
        if len(recent_patents) < 20:
            recent_patents.append(
                {
                    "patent_number": number,
                    "title": title,
                    "date": date_str,
                    "url": f"https://patents.google.com/patent/{number}" if number else "",
                }
            )

    total = len(matched)
    return {
        "total_patents": total,
        "recent_patents": recent_patents,
        "patent_velocity": velocity,
        "ip_score": _ip_score(total, velocity),
    }


def _gp_get(url: str) -> dict | None:
    """GET the Google Patents XHR endpoint as JSON, retrying once on a 503/blip."""
    import time

    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
                return r.json() or {}
        except Exception:
            pass
        if attempt < 2:
            time.sleep(1.0 + attempt)  # brief backoff on throttle
    return None


def _assignee_str(assignee) -> str:
    if isinstance(assignee, list):
        return " ".join(str(a) for a in assignee)
    return str(assignee or "")


def _parse_patent_date(s: str):
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None
