from core.models import AgentOutput
from tools.uspto_tool import fetch_patents_data


class PatentsAgent:
    agent_name = "patents"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_patents_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["https://patents.google.com"],
            )

        total = int(data.get("total_patents", 0))
        velocity = int(data.get("patent_velocity", 0))
        ip_score = float(data.get("ip_score", 0.0) or 0.0)
        recent = data.get("recent_patents") or []

        # Use ip_score from tool as starting point, then blend velocity signal
        score = ip_score
        if velocity > 0 and total > 0:
            recent_ratio = velocity / total
            if recent_ratio >= 0.3:
                score = min(10.0, score + 1.0)
            elif recent_ratio >= 0.1:
                score = min(10.0, score + 0.5)
        score = round(max(0.0, min(10.0, score)), 2)

        red_flags: list[str] = []
        green_flags: list[str] = []

        if total == 0:
            red_flags.append("No patents filed under this assignee — possible IP gap for a later-stage company")
        elif velocity == 0 and total > 0:
            red_flags.append("Patent portfolio exists but no filings in the last 12 months")

        if velocity >= 3:
            green_flags.append(f"Patent velocity increasing — {velocity} filings in the last 12 months")
        if total >= 10:
            green_flags.append(f"Substantial IP portfolio ({total} total patents)")

        sources = ["https://patents.google.com"]
        for p in recent[:10]:
            url = p.get("url")
            if url:
                sources.append(url)

        status = "success" if total > 0 else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={**data, "red_flags": red_flags, "green_flags": green_flags},
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return PatentsAgent().run(company_name, sector)
