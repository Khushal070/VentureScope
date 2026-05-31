import os
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
ADZUNA_API_BASE = "https://api.adzuna.com/v1/api"
TIMEOUT = 15

DEPARTMENT_KEYWORDS = {
    "engineering": [
        "engineer", "developer", "software", "sre", "devops", "data",
        "ml", "machine learning", "ai", "infrastructure", "platform",
        "backend", "frontend", "full stack", "fullstack", "qa",
        "security", "architect",
    ],
    "product": [
        "product manager", "product owner", "product designer",
        "ux", "ui", "user experience", "designer", "research",
    ],
    "sales": [
        "sales", "account executive", "account manager", "business development",
        "bdr", "sdr", "revenue", "growth", "partnerships",
    ],
    "ops": [
        "operations", "finance", "hr", "people", "recruiter", "legal",
        "marketing", "support", "customer success", "admin",
    ],
}


def _empty_result() -> dict:
    return {
        "total_jobs": 0,
        "jobs_by_department": {"engineering": 0, "product": 0, "sales": 0, "ops": 0},
        "recent_postings": [],
        "hiring_velocity": 0.0,
    }


def _classify(title: str) -> str:
    t = (title or "").lower()
    for dept, kws in DEPARTMENT_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return dept
    return "ops"


def _fetch_page(company_name: str, page: int, days: int) -> list[dict]:
    try:
        r = requests.get(
            f"{ADZUNA_API_BASE}/jobs/us/search/{page}",
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": company_name,
                "company": company_name,
                "results_per_page": 50,
                "max_days_old": days,
                "content-type": "application/json",
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        return (r.json() or {}).get("results", []) or []
    except Exception:
        return []


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _fetch_linkedin_jobs_data(company_name: str) -> dict:
    """Fallback hiring signal scraped from LinkedIn's public guest jobs."""
    try:
        from tools.linkedin_tool import fetch_company_jobs

        jobs = fetch_company_jobs(company_name, max_jobs=25)
    except Exception:
        jobs = []
    if not jobs:
        return _empty_result()

    dept_counts = Counter()
    recent_postings: list[dict] = []
    for j in jobs:
        title = j.get("title", "") or ""
        dept_counts[_classify(title)] += 1
        recent_postings.append(
            {"title": title, "date": None, "location": j.get("location")}
        )

    return {
        "total_jobs": len(jobs),
        "jobs_by_department": {
            "engineering": dept_counts.get("engineering", 0),
            "product": dept_counts.get("product", 0),
            "sales": dept_counts.get("sales", 0),
            "ops": dept_counts.get("ops", 0),
        },
        "recent_postings": recent_postings[:20],
        "hiring_velocity": 0.0,  # LinkedIn guest data has no reliable dates
        "source": "linkedin",
    }


def fetch_jobs_data(company_name: str) -> dict:
    """Hiring signal from Adzuna, falling back to LinkedIn when Adzuna is empty."""
    adzuna = _fetch_adzuna(company_name)
    if adzuna.get("total_jobs", 0) > 0:
        return adzuna
    # Adzuna returned nothing (no keys, no coverage) → try LinkedIn.
    linkedin = _fetch_linkedin_jobs_data(company_name)
    return linkedin if linkedin.get("total_jobs", 0) > 0 else adzuna


def _fetch_adzuna(company_name: str) -> dict:
    if not company_name or not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return _empty_result()

    results = _fetch_page(company_name, page=1, days=60)
    if not results:
        return _empty_result()

    company_lower = company_name.lower()
    filtered = [
        j for j in results
        if company_lower in (j.get("company", {}).get("display_name", "") or "").lower()
    ]
    if not filtered:
        filtered = results

    dept_counts = Counter()
    recent_postings: list[dict] = []
    now = datetime.now(timezone.utc)
    this_month_cutoff = now - timedelta(days=30)
    last_month_cutoff = now - timedelta(days=60)

    this_month = 0
    last_month = 0

    for job in filtered:
        title = job.get("title", "") or ""
        dept = _classify(title)
        dept_counts[dept] += 1

        created = _parse_date(job.get("created"))
        if created:
            if created >= this_month_cutoff:
                this_month += 1
            elif created >= last_month_cutoff:
                last_month += 1

        recent_postings.append(
            {
                "title": title,
                "date": job.get("created"),
                "location": (job.get("location") or {}).get("display_name"),
            }
        )

    recent_postings.sort(key=lambda x: x.get("date") or "", reverse=True)
    recent_postings = recent_postings[:20]

    if last_month == 0:
        hiring_velocity = float(this_month)
    else:
        hiring_velocity = round((this_month - last_month) / last_month, 2)

    return {
        "total_jobs": len(filtered),
        "jobs_by_department": {
            "engineering": dept_counts.get("engineering", 0),
            "product": dept_counts.get("product", 0),
            "sales": dept_counts.get("sales", 0),
            "ops": dept_counts.get("ops", 0),
        },
        "recent_postings": recent_postings,
        "hiring_velocity": hiring_velocity,
    }
