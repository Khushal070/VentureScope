"""Best-effort LinkedIn public ("guest") jobs scraper.

LinkedIn exposes an unauthenticated guest endpoint that returns job-card HTML.
We use it as a fallback when Adzuna has no results (hiring signal) and to infer
a tech stack from job descriptions when a company has no public GitHub activity.

Everything here degrades gracefully: any network/parse failure returns empty
results so callers can fall back to their own safe defaults.
"""

import re

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
_GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_GUEST_POSTING = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
_TIMEOUT = 15


def _company_matches(card_company: str, company_name: str) -> bool:
    """Loosely match a job card's company to the searched company."""
    c = (card_company or "").lower()
    name = company_name.lower()
    if name in c or c in name:
        return True
    first = name.split()[0] if name.split() else name
    return bool(first) and first in c


def fetch_linkedin_jobs(company_name: str, max_jobs: int = 25) -> list[dict]:
    """Return a list of {title, company, location, job_id, url} job cards."""
    if not company_name:
        return []
    try:
        from bs4 import BeautifulSoup

        r = requests.get(
            _GUEST_SEARCH,
            params={"keywords": company_name, "location": "United States", "start": 0},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs: list[dict] = []
    for li in soup.find_all("li")[:max_jobs]:
        title_el = li.find(class_=re.compile("base-search-card__title"))
        sub_el = li.find(class_=re.compile("base-search-card__subtitle"))
        loc_el = li.find(class_=re.compile("job-search-card__location"))
        urn_el = li.find(attrs={"data-entity-urn": True})
        a_el = li.find("a", href=True)

        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue
        job_id = None
        if urn_el:
            m = re.search(r"(\d+)", urn_el.get("data-entity-urn", ""))
            job_id = m.group(1) if m else None
        jobs.append(
            {
                "title": title,
                "company": sub_el.get_text(strip=True) if sub_el else "",
                "location": loc_el.get_text(strip=True) if loc_el else None,
                "job_id": job_id,
                "url": a_el["href"].split("?")[0] if a_el else None,
            }
        )
    return jobs


def fetch_company_jobs(company_name: str, max_jobs: int = 25) -> list[dict]:
    """LinkedIn jobs filtered to cards that actually belong to the company."""
    jobs = fetch_linkedin_jobs(company_name, max_jobs=max_jobs)
    matched = [j for j in jobs if _company_matches(j.get("company", ""), company_name)]
    return matched or jobs  # fall back to unfiltered if nothing matched


def fetch_job_description(job_id: str | None) -> str:
    """Fetch the plain-text description for a single guest job posting."""
    if not job_id:
        return ""
    try:
        from bs4 import BeautifulSoup

        r = requests.get(
            f"{_GUEST_POSTING}{job_id}", headers=_HEADERS, timeout=_TIMEOUT
        )
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        desc = soup.find(
            class_=re.compile("description__text|show-more-less-html__markup")
        )
        return (desc or soup).get_text(" ", strip=True)
    except Exception:
        return ""
