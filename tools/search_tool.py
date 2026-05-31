"""Founder research tool.

Primary source is **Wikipedia** (no API key required): it finds the company's
article, parses the infobox for founders, and pulls each founder's intro for
background. If Wikipedia yields nothing, it falls back to Gemini (only when
``GEMINI_API_KEY`` is set).
"""

import json
import os
import re

import requests
import weave
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOKENS = 2048

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "VentureScope/1.0 (angel-investor research)"}
TIMEOUT = 15


def _wiki_get(params: dict) -> dict | None:
    """GET the Wikipedia API as JSON, with one retry on transient failure."""
    import time

    for attempt in range(2):
        try:
            r = requests.get(
                WIKI_API, params=params, headers=WIKI_HEADERS, timeout=TIMEOUT
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        if attempt == 0:
            time.sleep(0.6)  # back off briefly on throttle / blip
    return None


SYSTEM_PROMPT = (
    "You are a research assistant for an angel investor. "
    "Using your knowledge, find founder information for the named company. "
    "Return ONLY a single JSON object — no prose, no markdown — matching this schema:\n"
    "{\n"
    '  "founders": [\n'
    '    {\n'
    '      "name": "string",\n'
    '      "role": "string",\n'
    '      "background": "1-2 sentence summary",\n'
    '      "previous_companies": ["string"],\n'
    '      "education": ["string"]\n'
    '    }\n'
    "  ],\n"
    '  "founder_score": 0.0,\n'
    '  "serial_entrepreneur": false\n'
    "}\n"
    "founder_score is 0-10 based on prior exits, brand-name companies, and experience depth. "
    "serial_entrepreneur is true if any founder has ≥2 prior founded companies or ≥1 exit. "
    "If no founders can be found, return an empty founders list with founder_score 0 and "
    "serial_entrepreneur false."
)


def _empty_result() -> dict:
    return {
        "founders": [],
        "founder_score": 0.0,
        "serial_entrepreneur": False,
    }


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _normalize(parsed: dict | None) -> dict:
    if not isinstance(parsed, dict):
        return _empty_result()
    founders_raw = parsed.get("founders") or []
    founders: list[dict] = []
    if isinstance(founders_raw, list):
        for f in founders_raw:
            if not isinstance(f, dict):
                continue
            founders.append(
                {
                    "name": str(f.get("name") or ""),
                    "role": str(f.get("role") or ""),
                    "background": str(f.get("background") or ""),
                    "previous_companies": [
                        str(c) for c in (f.get("previous_companies") or [])
                        if isinstance(c, (str, int, float))
                    ],
                    "education": [
                        str(e) for e in (f.get("education") or [])
                        if isinstance(e, (str, int, float))
                    ],
                }
            )

    try:
        founder_score = float(parsed.get("founder_score", 0.0) or 0.0)
    except Exception:
        founder_score = 0.0
    founder_score = max(0.0, min(10.0, founder_score))

    serial = bool(parsed.get("serial_entrepreneur", False))

    return {
        "founders": founders,
        "founder_score": round(founder_score, 2),
        "serial_entrepreneur": serial,
    }


# --------------------------------------------------------------------------- #
# Wikipedia (no API key)
# --------------------------------------------------------------------------- #
def _looks_like_name(s: str) -> bool:
    s = (s or "").strip()
    if len(s) < 3 or len(s) > 60:
        return False
    if any(ch.isdigit() for ch in s) or "[" in s or "(" in s:
        return False
    # At least two capitalized words (first + last name).
    return bool(re.match(r"^[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+)+$", s))


def _wiki_search_titles(company_name: str, limit: int = 5) -> list[str]:
    """Return candidate article titles, biased toward the company page.

    A bare search for e.g. "Stripe" returns the generic article first, not
    "Stripe (company)", so we prepend explicit company-page guesses and then
    append the raw search hits.
    """
    titles: list[str] = [f"{company_name} (company)", company_name]
    data = _wiki_get(
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{company_name} company",
            "srlimit": limit,
            "format": "json",
        }
    )
    if data:
        for hit in (data.get("query") or {}).get("search") or []:
            t = hit.get("title")
            if t:
                titles.append(t)
    seen: set[str] = set()
    ordered = [t for t in titles if t and not (t in seen or seen.add(t))]
    return ordered[:4]  # cap parse calls per company


def _wiki_founder_names(title: str) -> list[str]:
    from bs4 import BeautifulSoup

    data = _wiki_get(
        {
            "action": "parse",
            "page": title,
            "prop": "text",
            "redirects": 1,
            "format": "json",
        }
    )
    html = (((data or {}).get("parse") or {}).get("text") or {}).get("*") or ""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    infobox = soup.find("table", class_=lambda c: bool(c) and "infobox" in c)
    if not infobox:
        return []

    names: list[str] = []
    for row in infobox.find_all("tr"):
        header = row.find("th")
        if not header:
            continue
        h = header.get_text(" ", strip=True).lower()
        if "founder" not in h and "founded by" not in h:
            continue
        cell = row.find("td")
        if not cell:
            continue
        for sup in cell.find_all("sup"):  # drop citation markers
            sup.decompose()

        raw_names: list[str] = []
        items = cell.find_all("li")
        anchors = cell.find_all("a")
        if items:
            for li in items:
                a = li.find("a")
                raw_names.append((a.get_text(strip=True) if a else li.get_text(strip=True)))
        elif anchors:
            raw_names = [a.get_text(strip=True) for a in anchors]
        else:
            raw_names = [
                part.strip()
                for part in cell.get_text("\n", strip=True).split("\n")
                if part.strip()
            ]

        for n in raw_names:
            if _looks_like_name(n) and n not in names:
                names.append(n)
        if names:
            break

    return names[:5]


def _wiki_intros(names: list[str]) -> dict:
    if not names:
        return {}
    data = _wiki_get(
        {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": "|".join(names),
            "format": "json",
        }
    )
    pages = ((data or {}).get("query") or {}).get("pages") or {} if data else {}
    out: dict = {}
    for p in pages.values():
        title = (p.get("title") or "").lower()
        extract = p.get("extract") or ""
        if title and extract:
            out[title] = extract
    return out


def _fetch_wikipedia(company_name: str) -> dict | None:
    names: list[str] = []
    for title in _wiki_search_titles(company_name):
        try:
            names = _wiki_founder_names(title)
        except Exception:
            names = []
        if names:
            break
    if not names:
        return None

    intros = _wiki_intros(names)
    founders: list[dict] = []
    for n in names:
        bg = (intros.get(n.lower()) or "").strip()
        founders.append(
            {
                "name": n,
                "role": "Founder",
                "background": bg[:400],
                "previous_companies": [],
                "education": [],
            }
        )

    blob = " ".join(f["background"].lower() for f in founders)
    serial = (
        "serial entrepreneur" in blob
        or sum(f["background"].lower().count("founded") for f in founders) >= 2
    )
    base_score = min(6.0, 3.0 + len(founders))  # Wikipedia-notable → modest base

    return _normalize(
        {
            "founders": founders,
            "founder_score": base_score,
            "serial_entrepreneur": serial,
        }
    )


# --------------------------------------------------------------------------- #
# Gemini fallback
# --------------------------------------------------------------------------- #
def _extract_text(response) -> str:
    """Pull text out of a Gemini ``generate_content`` response defensively."""
    try:
        if response.text:
            return response.text.strip()
    except Exception:
        pass
    parts: list[str] = []
    for cand in getattr(response, "candidates", []) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", []) or []:
            if getattr(part, "text", None):
                parts.append(part.text)
    return "\n".join(parts).strip()


def _fetch_gemini(company_name: str) -> dict | None:
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return None

    user_prompt = (
        f"Find the founders of {company_name}. For each founder, identify their "
        "current role, brief professional background, previous companies they "
        "worked at or founded, and education. Then assess whether any founder is "
        "a serial entrepreneur and compute a founder_score (0-10) reflecting prior "
        "exits, pedigree, and experience. Return only the JSON object."
    )
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        message = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=MAX_TOKENS,
                temperature=0.2,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
    except Exception:
        return None
    return _normalize(_parse_json(_extract_text(message)))


@weave.op()
def fetch_founder_data(company_name: str) -> dict:
    if not company_name:
        return _empty_result()

    # 1) Wikipedia — works with no API key.
    try:
        wiki = _fetch_wikipedia(company_name)
    except Exception:
        wiki = None
    if wiki and wiki.get("founders"):
        return wiki

    # 2) Gemini fallback (only if a key is configured).
    if GEMINI_API_KEY:
        gem = _fetch_gemini(company_name)
        if gem and gem.get("founders"):
            return gem

    return _empty_result()
