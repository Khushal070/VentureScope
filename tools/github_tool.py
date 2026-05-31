import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"
USER_AGENT = "VentureScope/1.0"
TIMEOUT = 15


def _headers() -> dict:
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _empty_result() -> dict:
    return {
        "org_name": None,
        "total_commits_30d": 0,
        "prev_commits_30d": 0,
        "top_repos": [],
        "contributor_count": 0,
        "stars_total": 0,
        "languages": {},
    }


def _get_org(login: str) -> dict | None:
    """Fetch an org by exact login slug; return its JSON or None if not found."""
    if not login:
        return None
    try:
        r = requests.get(
            f"{GITHUB_API_BASE}/orgs/{login}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def _candidate_slugs(company_name: str) -> list[str]:
    """Likely GitHub org slugs for a company name, most-specific first.

    e.g. "Perplexity AI" -> ["perplexity-ai", "perplexityai", "perplexity"].
    """
    low = company_name.strip().lower()
    tokens = low.split()
    cands = [
        low.replace(" ", "-").replace(".", ""),  # perplexity-ai
        low.replace(" ", "").replace(".", ""),   # perplexityai
    ]
    if tokens:
        cands.append(tokens[0])  # perplexity (drop trailing "ai"/"inc"/etc.)
    seen: set[str] = set()
    return [c for c in cands if c and not (c in seen or seen.add(c))]


def _search_org(company_name: str) -> dict | None:
    candidates = _candidate_slugs(company_name)

    # 1) Try the candidate slugs directly against /orgs/{slug} (exact, cheap).
    for slug in candidates:
        org = _get_org(slug)
        if org:
            return org

    # 2) Fall back to GitHub user search, preferring a login that matches a
    #    candidate slug or starts with the company's first token.
    try:
        r = requests.get(
            f"{GITHUB_API_BASE}/search/users",
            params={"q": f"{company_name} type:org", "per_page": 10},
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        items = r.json().get("items", []) or []
    except Exception:
        return None

    if not items:
        return None

    first = (company_name.strip().lower().split() or [""])[0]
    logins = [it.get("login") for it in items if it.get("login")]

    def _rank(login: str) -> int:
        ll = login.lower()
        if ll in candidates:
            return 0
        if first and ll.startswith(first):
            return 1
        if first and first in ll:
            return 2
        return 3

    for login in sorted(logins, key=_rank):
        org = _get_org(login)
        if org:
            return org

    # Last resort: return the top hit's login even without org details.
    return {"login": logins[0]} if logins else None


def _list_repos(org_login: str, limit: int = 5) -> list[dict]:
    try:
        r = requests.get(
            f"{GITHUB_API_BASE}/orgs/{org_login}/repos",
            params={"per_page": 100, "type": "public", "sort": "updated"},
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        repos = r.json() or []
        repos.sort(key=lambda x: x.get("stargazers_count", 0), reverse=True)
        return repos[:limit]
    except Exception:
        return []


def _commit_buckets(owner: str, repo: str) -> tuple[int, int]:
    """Return (commits_last_30d, commits_prev_30d) using stats/participation."""
    try:
        r = requests.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/stats/participation",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return 0, 0
        weekly = (r.json() or {}).get("all", [])
        if len(weekly) < 8:
            return sum(weekly[-4:]) if weekly else 0, 0
        return sum(weekly[-4:]), sum(weekly[-8:-4])
    except Exception:
        return 0, 0


def _contributor_count(owner: str, repo: str) -> int:
    try:
        r = requests.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contributors",
            params={"per_page": 1, "anon": "true"},
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return 0
        link = r.headers.get("Link", "")
        if 'rel="last"' in link:
            for part in link.split(","):
                if 'rel="last"' in part:
                    try:
                        page = int(part.split("page=")[1].split(">")[0].split("&")[0])
                        return page
                    except Exception:
                        return len(r.json() or [])
        return len(r.json() or [])
    except Exception:
        return 0


def _repo_languages(owner: str, repo: str) -> dict:
    try:
        r = requests.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/languages",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return {}
        return r.json() or {}
    except Exception:
        return {}


def fetch_github_data(company_name: str) -> dict:
    if not company_name:
        return _empty_result()

    org = _search_org(company_name)
    if not org:
        return _empty_result()

    org_login = org.get("login")
    if not org_login:
        return _empty_result()

    repos = _list_repos(org_login, limit=5)
    if not repos:
        return {**_empty_result(), "org_name": org_login}

    total_commits_30d = 0
    prev_commits_30d = 0
    contributor_total = 0
    stars_total = 0
    languages_agg: dict[str, int] = {}
    top_repos: list[dict] = []

    for repo in repos:
        name = repo.get("name")
        if not name:
            continue
        stars = int(repo.get("stargazers_count", 0))
        forks = int(repo.get("forks_count", 0))
        stars_total += stars

        c30, cprev = _commit_buckets(org_login, name)
        total_commits_30d += c30
        prev_commits_30d += cprev

        contributor_total += _contributor_count(org_login, name)

        for lang, byte_count in _repo_languages(org_login, name).items():
            languages_agg[lang] = languages_agg.get(lang, 0) + int(byte_count)

        pushed_at = repo.get("pushed_at")
        top_repos.append(
            {
                "name": name,
                "full_name": repo.get("full_name"),
                "url": repo.get("html_url"),
                "stars": stars,
                "forks": forks,
                "open_issues": int(repo.get("open_issues_count", 0)),
                "primary_language": repo.get("language"),
                "commits_30d": c30,
                "pushed_at": pushed_at,
            }
        )

    return {
        "org_name": org_login,
        "total_commits_30d": total_commits_30d,
        "prev_commits_30d": prev_commits_30d,
        "top_repos": top_repos,
        "contributor_count": contributor_total,
        "stars_total": stars_total,
        "languages": languages_agg,
    }
