from core.models import AgentOutput
from tools.newsapi_tool import fetch_news_data

RED_KEYWORDS = ["lawsuit", "layoff", "layoffs", "fraud", "pivot", "fired", "shutdown", "bankruptcy"]
GREEN_KEYWORDS = [
    "funding", "raised", "raises", "series a", "series b", "series c",
    "launch", "launches", "launched", "user growth", "milestone",
    "partnership", "acquired", "acquires", "ipo",
]


class NewsAgent:
    agent_name = "news"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_news_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["https://newsapi.org/v2/everything"],
            )

        total = int(data.get("total_articles", 0))
        sentiment = float(data.get("sentiment_score", 0.0) or 0.0)
        top_articles = data.get("top_articles") or []
        themes = data.get("key_themes") or []

        # Map sentiment [-1, 1] -> [0, 10]
        sentiment_clamped = max(-1.0, min(1.0, sentiment))
        score = round(5.0 + sentiment_clamped * 5.0, 2)

        # Boost if volume is healthy and sentiment positive
        if total >= 20 and sentiment > 0:
            score = min(10.0, score + 0.5)
        if total == 0:
            score = 0.0

        red_flags: list[str] = []
        green_flags: list[str] = []
        red_hits: list[str] = []
        green_hits: list[str] = []

        for art in top_articles:
            title = (art.get("title") or "").lower()
            for kw in RED_KEYWORDS:
                if kw in title:
                    red_hits.append(art.get("title") or "")
                    break
            for kw in GREEN_KEYWORDS:
                if kw in title:
                    green_hits.append(art.get("title") or "")
                    break

        if total == 0:
            red_flags.append("No news coverage in the last 30 days")
        if red_hits:
            red_flags.append(
                f"Negative coverage signals: {len(red_hits)} article(s) mention "
                "lawsuits, layoffs, fraud, or pivots"
            )
        if green_hits:
            green_flags.append(
                f"Positive coverage: {len(green_hits)} article(s) mention "
                "funding, launches, or growth"
            )
        if total >= 20 and sentiment > 0.2:
            green_flags.append(
                f"Strong positive media presence ({total} articles, sentiment {sentiment:+.2f})"
            )

        sources = ["https://newsapi.org/v2/everything"]
        for a in top_articles[:10]:
            url = a.get("url")
            if url:
                sources.append(url)

        status = "success" if total > 0 else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={
                **data,
                "red_flag_headlines": red_hits[:5],
                "green_flag_headlines": green_hits[:5],
                "red_flags": red_flags,
                "green_flags": green_flags,
                "themes_summary": themes[:8],
            },
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return NewsAgent().run(company_name, sector)
