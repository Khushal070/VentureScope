from core.models import AgentOutput
from tools.techstack_tool import fetch_techstack_data

MODERN_LANGS = {"Python", "TypeScript", "Go", "Rust", "Kotlin", "Swift", "Scala", "Elixir"}
SOLID_LANGS = {"JavaScript", "Java", "C++", "C#", "Ruby", "Dart"}
LEGACY_LANGS = {"COBOL", "Visual Basic", "VB.NET", "ASP", "ColdFusion", "Perl", "Pascal", "Fortran"}
ML_INDICATORS = {"Jupyter Notebook", "Python", "Cuda", "R", "Julia"}


class TechStackAgent:
    agent_name = "techstack"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_techstack_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["https://api.github.com"],
            )

        primary = data.get("primary_language")
        languages = data.get("languages") or {}
        categories = data.get("tech_categories") or {}
        repo_count = int(data.get("repo_count", 0))
        avg_stars = float(data.get("avg_repo_stars", 0.0) or 0.0)

        ml_pct = float(categories.get("ml", 0.0) or 0.0)

        # Modernity (0-4)
        modern_pct = sum(pct for lang, pct in languages.items() if lang in MODERN_LANGS)
        solid_pct = sum(pct for lang, pct in languages.items() if lang in SOLID_LANGS)
        legacy_pct = sum(pct for lang, pct in languages.items() if lang in LEGACY_LANGS)

        if modern_pct >= 50:
            modernity = 4.0
        elif modern_pct >= 25:
            modernity = 3.0
        elif modern_pct + solid_pct >= 50:
            modernity = 2.0
        elif languages:
            modernity = 1.0
        else:
            modernity = 0.0
        if legacy_pct >= 30:
            modernity = max(0.0, modernity - 1.5)

        # ML/AI presence (0-3)
        has_ml = any(l in languages for l in ML_INDICATORS) or ml_pct >= 10
        if ml_pct >= 30:
            ml_score = 3.0
        elif ml_pct >= 10:
            ml_score = 2.0
        elif has_ml:
            ml_score = 1.0
        else:
            ml_score = 0.0

        # Activity (0-3)
        if repo_count >= 5 and avg_stars >= 100:
            activity = 3.0
        elif repo_count >= 3 and avg_stars >= 10:
            activity = 2.0
        elif repo_count > 0:
            activity = 1.0
        else:
            activity = 0.0

        score = round(min(10.0, modernity + ml_score + activity), 2)

        red_flags: list[str] = []
        green_flags: list[str] = []

        if not languages:
            red_flags.append("No detectable tech stack from public repos")
        if legacy_pct >= 30:
            red_flags.append(f"Legacy languages dominate ({round(legacy_pct)}% of codebase)")
        if not has_ml and ml_pct == 0 and (sector or "").lower() in {"ai", "ml", "machine learning"}:
            red_flags.append("Claimed AI/ML sector but no ML indicators in code")

        if has_ml:
            green_flags.append(
                f"AI/ML technologies present (Python/Jupyter/Cuda share: {round(ml_pct)}%)"
            )
        if modern_pct >= 50:
            green_flags.append(f"Modern stack ({round(modern_pct)}% in Python/TS/Go/Rust)")
        if avg_stars >= 100 and repo_count >= 3:
            green_flags.append(
                f"Active repos with traction ({repo_count} repos, avg {round(avg_stars)} stars)"
            )

        sources = ["https://api.github.com/repos/{owner}/{repo}/languages"]

        status = "success" if languages else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={
                **data,
                "modern_pct": round(modern_pct, 2),
                "legacy_pct": round(legacy_pct, 2),
                "has_ml": has_ml,
                "red_flags": red_flags,
                "green_flags": green_flags,
            },
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return TechStackAgent().run(company_name, sector)
