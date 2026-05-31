import re

from tools.github_tool import fetch_github_data

# Tech keywords scanned in job descriptions -> (canonical language, category).
# A None language means the keyword only contributes to the category signal.
TECH_KEYWORDS: dict[str, tuple[str | None, str]] = {
    "python": ("Python", "backend"), "django": ("Python", "backend"),
    "flask": ("Python", "backend"), "fastapi": ("Python", "backend"),
    "pytorch": ("Python", "ml"), "tensorflow": ("Python", "ml"),
    "machine learning": (None, "ml"), "deep learning": (None, "ml"),
    "llm": (None, "ml"), "nlp": (None, "ml"), "transformers": (None, "ml"),
    "react": ("TypeScript", "frontend"), "next.js": ("TypeScript", "frontend"),
    "nextjs": ("TypeScript", "frontend"), "typescript": ("TypeScript", "frontend"),
    "javascript": ("JavaScript", "frontend"), "vue": ("TypeScript", "frontend"),
    "svelte": ("TypeScript", "frontend"), "tailwind": (None, "frontend"),
    "node.js": ("TypeScript", "backend"), "nodejs": ("TypeScript", "backend"),
    "golang": ("Go", "backend"), "rust": ("Rust", "backend"),
    "java": ("Java", "backend"), "kotlin": ("Kotlin", "backend"),
    "swift": ("Swift", "frontend"), "ruby": ("Ruby", "backend"),
    "rails": ("Ruby", "backend"), "scala": ("Scala", "backend"),
    "c++": ("C++", "backend"), "elixir": ("Elixir", "backend"),
    "kubernetes": (None, "devops"), "docker": (None, "devops"),
    "terraform": (None, "devops"), "aws": (None, "devops"),
    "gcp": (None, "devops"), "azure": (None, "devops"),
}


def _infer_from_jobs(company_name: str) -> dict | None:
    """Infer a tech stack from LinkedIn job descriptions.

    Fallback for companies (e.g. closed-source) with no public GitHub activity.
    """
    try:
        from tools.linkedin_tool import fetch_company_jobs, fetch_job_description

        jobs = fetch_company_jobs(company_name, max_jobs=10)
    except Exception:
        return None
    if not jobs:
        return None

    texts = [j.get("title", "") for j in jobs]
    for j in jobs[:5]:  # pull a few full descriptions for keyword density
        desc = fetch_job_description(j.get("job_id"))
        if desc:
            texts.append(desc)
    blob = " ".join(texts).lower()
    if not blob.strip():
        return None

    lang_counts: dict[str, int] = {}
    cat_counts: dict[str, float] = {"frontend": 0.0, "backend": 0.0, "ml": 0.0, "devops": 0.0}
    for kw, (lang, cat) in TECH_KEYWORDS.items():
        hits = len(re.findall(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", blob))
        if hits:
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + hits
            cat_counts[cat] += hits

    if not lang_counts and not any(cat_counts.values()):
        return None

    total_lang = sum(lang_counts.values()) or 1
    languages_pct = {
        lang: round(100.0 * c / total_lang, 2)
        for lang, c in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
    }
    total_cat = sum(cat_counts.values()) or 1
    tech_categories = {k: round(100.0 * v / total_cat, 2) for k, v in cat_counts.items()}

    return {
        "primary_language": next(iter(languages_pct), None),
        "languages": languages_pct,
        "tech_categories": tech_categories,
        "repo_count": 0,
        "avg_repo_stars": 0.0,
        "source": "linkedin-jobs",
    }

FRONTEND = {
    "JavaScript", "TypeScript", "HTML", "CSS", "SCSS", "Sass", "Less",
    "Vue", "Svelte", "Astro", "CoffeeScript", "Stylus",
}
BACKEND = {
    "Python", "Go", "Java", "Kotlin", "Ruby", "PHP", "C#", "C++", "C",
    "Rust", "Scala", "Elixir", "Erlang", "Clojure", "Haskell", "OCaml",
    "F#", "Perl", "Lua", "Dart", "Crystal",
}
ML = {
    "Jupyter Notebook", "Python", "R", "Julia", "Cuda", "MATLAB",
}
DEVOPS = {
    "Shell", "Dockerfile", "HCL", "Makefile", "Nix", "Puppet", "PowerShell",
    "Batchfile", "Roff", "Smarty",
}


def _empty_result() -> dict:
    return {
        "primary_language": None,
        "languages": {},
        "tech_categories": {"frontend": 0.0, "backend": 0.0, "ml": 0.0, "devops": 0.0},
        "repo_count": 0,
        "avg_repo_stars": 0.0,
    }


def _categorize(languages_pct: dict[str, float]) -> dict[str, float]:
    cats = {"frontend": 0.0, "backend": 0.0, "ml": 0.0, "devops": 0.0}
    for lang, pct in languages_pct.items():
        if lang in FRONTEND:
            cats["frontend"] += pct
        if lang in BACKEND:
            cats["backend"] += pct
        if lang in ML:
            cats["ml"] += pct
        if lang in DEVOPS:
            cats["devops"] += pct
    return {k: round(v, 2) for k, v in cats.items()}


def fetch_techstack_data(company_name: str) -> dict:
    if not company_name:
        return _empty_result()

    try:
        gh = fetch_github_data(company_name)
    except Exception:
        return _empty_result()

    languages_bytes: dict[str, int] = gh.get("languages") or {}
    repos = gh.get("top_repos") or []

    # No detectable public GitHub stack → infer from job postings instead.
    if not languages_bytes:
        inferred = _infer_from_jobs(company_name)
        if inferred:
            return inferred
        if not repos:
            return _empty_result()

    total_bytes = sum(languages_bytes.values()) or 1
    languages_pct = {
        lang: round(100.0 * bytes_ / total_bytes, 2)
        for lang, bytes_ in languages_bytes.items()
    }
    languages_pct = dict(
        sorted(languages_pct.items(), key=lambda x: x[1], reverse=True)
    )

    primary_language = next(iter(languages_pct), None)
    repo_count = len(repos)
    avg_stars = (
        round(sum(int(r.get("stars", 0)) for r in repos) / repo_count, 2)
        if repo_count
        else 0.0
    )

    return {
        "primary_language": primary_language,
        "languages": languages_pct,
        "tech_categories": _categorize(languages_pct),
        "repo_count": repo_count,
        "avg_repo_stars": avg_stars,
    }
