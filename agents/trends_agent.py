from core.models import AgentOutput
from tools.trends_tool import fetch_trends_data


class TrendsAgent:
    agent_name = "trends"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_trends_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["https://trends.google.com"],
            )

        current = int(data.get("current_interest", 0))
        avg = int(data.get("avg_interest", 0))
        peak = int(data.get("peak_interest", 0))
        direction = str(data.get("trend_direction", "stable") or "stable")
        monthly = data.get("monthly_data") or []

        # Blend current and avg, then nudge by direction
        base = 0.7 * current + 0.3 * avg  # 0-100
        score = base / 10.0  # 0-10
        if direction == "rising":
            score += 1.0
        elif direction == "falling":
            score -= 1.0
        score = round(max(0.0, min(10.0, score)), 2)

        red_flags: list[str] = []
        green_flags: list[str] = []

        if not monthly:
            red_flags.append("No Google Trends data available for this term")
        elif direction == "falling":
            red_flags.append(f"Search interest trending down (current {current}, peak {peak})")
        elif current == 0 and avg == 0:
            red_flags.append("Negligible search interest over the last 12 months")

        if direction == "rising":
            green_flags.append(f"Search interest rising (current {current}, avg {avg})")
        if peak >= 75:
            green_flags.append(f"High peak search interest reached ({peak}/100)")

        sources = ["https://trends.google.com"]

        status = "success" if monthly else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={**data, "red_flags": red_flags, "green_flags": green_flags},
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return TrendsAgent().run(company_name, sector)
