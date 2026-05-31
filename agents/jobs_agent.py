from core.models import AgentOutput
from tools.adzuna_tool import fetch_jobs_data


class JobsAgent:
    agent_name = "jobs"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_jobs_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["https://api.adzuna.com/v1/api"],
            )

        total = int(data.get("total_jobs", 0))
        depts = data.get("jobs_by_department") or {}
        eng = int(depts.get("engineering", 0))
        product = int(depts.get("product", 0))
        sales = int(depts.get("sales", 0))
        ops = int(depts.get("ops", 0))
        velocity = float(data.get("hiring_velocity", 0.0) or 0.0)

        # Volume (0-4)
        if total >= 100:
            vol = 4.0
        elif total >= 30:
            vol = 3.0
        elif total >= 10:
            vol = 2.0
        elif total > 0:
            vol = 1.0
        else:
            vol = 0.0

        # Engineering ratio (0-3)
        eng_ratio = (eng / total) if total > 0 else 0.0
        if eng_ratio >= 0.6:
            eng_score = 3.0
        elif eng_ratio >= 0.4:
            eng_score = 2.0
        elif eng_ratio >= 0.2:
            eng_score = 1.0
        else:
            eng_score = 0.0

        # Velocity (0-3)
        if velocity >= 0.5:
            vel_score = 3.0
        elif velocity >= 0.2:
            vel_score = 2.0
        elif velocity > 0:
            vel_score = 1.0
        elif velocity == 0:
            vel_score = 0.5
        else:
            vel_score = 0.0

        score = round(min(10.0, vol + eng_score + vel_score), 2)

        red_flags: list[str] = []
        green_flags: list[str] = []

        sales_ratio = (sales / total) if total > 0 else 0.0

        if total == 0:
            red_flags.append("No open job postings found")
        if total > 0 and eng == 0 and sales > 0:
            red_flags.append("Only sales roles open — growth-over-product concern")
        if total > 0 and sales_ratio >= 0.7:
            red_flags.append(
                f"Sales-heavy hiring ({round(sales_ratio * 100)}% of open roles)"
            )

        if eng_ratio >= 0.6:
            green_flags.append(
                f"Product-first hiring ({round(eng_ratio * 100)}% engineering)"
            )
        if velocity >= 0.5:
            green_flags.append(f"Hiring accelerating ({round(velocity * 100)}% MoM)")
        if total >= 30:
            green_flags.append(f"Active recruiting at scale ({total} open roles)")

        sources = ["https://api.adzuna.com/v1/api/jobs/us/search/1"]

        status = "success" if total > 0 else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={**data, "red_flags": red_flags, "green_flags": green_flags},
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return JobsAgent().run(company_name, sector)
