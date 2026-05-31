from core.models import AgentOutput
from tools.github_tool import fetch_github_data


class GitHubAgent:
    agent_name = "github"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_github_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["https://api.github.com"],
            )

        commits = int(data.get("total_commits_30d", 0))
        prev = int(data.get("prev_commits_30d", 0))
        contribs = int(data.get("contributor_count", 0))
        stars = int(data.get("stars_total", 0))
        top_repos = data.get("top_repos") or []
        org = data.get("org_name")

        # Volume (0-3)
        if commits >= 200:
            vol = 3.0
        elif commits >= 50:
            vol = 2.5
        elif commits >= 10:
            vol = 2.0
        elif commits > 0:
            vol = 1.0
        else:
            vol = 0.0

        # Growth (0-3)
        if prev == 0:
            growth = 1.5 if commits > 0 else 0.0
            growth_pct = None
        else:
            growth_pct = (commits - prev) / prev
            if growth_pct > 0.5:
                growth = 3.0
            elif growth_pct > 0.2:
                growth = 2.25
            elif growth_pct > 0:
                growth = 1.5
            elif growth_pct > -0.2:
                growth = 1.0
            else:
                growth = 0.0

        # Contributors (0-2)
        if contribs > 50:
            contrib_score = 2.0
        elif contribs > 20:
            contrib_score = 1.5
        elif contribs > 5:
            contrib_score = 1.0
        elif contribs > 0:
            contrib_score = 0.5
        else:
            contrib_score = 0.0

        # Stars (0-2)
        if stars > 10000:
            star_score = 2.0
        elif stars > 1000:
            star_score = 1.5
        elif stars > 100:
            star_score = 1.0
        elif stars > 0:
            star_score = 0.5
        else:
            star_score = 0.0

        score = round(min(10.0, vol + growth + contrib_score + star_score), 2)

        red_flags: list[str] = []
        green_flags: list[str] = []

        if not org:
            red_flags.append("No public GitHub organization found")
        if commits == 0:
            red_flags.append("Zero commits across top repos in the last 30 days")
        if growth_pct is not None and growth_pct > 0.5:
            green_flags.append(
                f"Commit activity grew {round(growth_pct * 100)}% month-over-month"
            )
        if stars > 1000:
            green_flags.append(f"{stars:,} cumulative stars across top repos")
        if contribs > 20:
            green_flags.append(f"Healthy contributor base ({contribs} contributors)")

        sources = ["https://api.github.com/search/users"]
        for r in top_repos:
            url = r.get("url")
            if url:
                sources.append(url)

        status = "success" if org and (commits or stars or contribs) else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={**data, "red_flags": red_flags, "green_flags": green_flags},
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return GitHubAgent().run(company_name, sector)
