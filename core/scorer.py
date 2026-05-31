from core.models import AgentOutput, MomentumScore

# Weighting of each signal toward the overall momentum score.
# Tuned to stop penalizing large closed-source companies: GitHub/patents/tech
# stack (all public-code signals) are de-emphasized in favor of hiring, founders,
# news, and search demand. Weights total 1.05; the closed-source bonus can add
# more, so ``overall_momentum`` is clamped to [0, 10].
AGENT_WEIGHTS: dict[str, float] = {
    "github": 0.08,
    "jobs": 0.25,
    "news": 0.22,
    "patents": 0.05,
    "founder": 0.25,
    "trends": 0.15,
    "techstack": 0.05,
}

# Closed-source bonus: companies that are intentionally private about their code
# (strong hiring + positive press + proven founders) shouldn't be dragged down
# by empty public-code signals.
CLOSED_SOURCE_BONUS = 1.5
_BONUS_MIN_ROLES = 5
_BONUS_MIN_FOUNDER_SCORE = 6.0

# Maps an agent name to the MomentumScore field that holds its score.
_SCORE_FIELDS: dict[str, str] = {
    "github": "github_score",
    "jobs": "jobs_score",
    "news": "news_score",
    "patents": "patents_score",
    "founder": "founder_score",
    "trends": "trends_score",
    "techstack": "techstack_score",
}


class MomentumScorer:
    """Aggregates per-agent outputs into a weighted :class:`MomentumScore`.

    Each agent contributes a 0-10 score; the weighted sum (per
    :data:`AGENT_WEIGHTS`) becomes ``overall_momentum``. Red and green flags
    stashed in each agent's ``data`` dict are collected across all agents.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or AGENT_WEIGHTS

    def score(self, agent_outputs: list[AgentOutput]) -> MomentumScore:
        by_name = {out.agent_name: out for out in agent_outputs}

        per_agent_scores: dict[str, float] = {}
        overall = 0.0
        for name, field in _SCORE_FIELDS.items():
            out = by_name.get(name)
            agent_score = out.score if out is not None else 0.0
            per_agent_scores[field] = round(agent_score, 2)
            overall += agent_score * self.weights.get(name, 0.0)

        red_flags: list[str] = []
        green_flags: list[str] = []
        for out in agent_outputs:
            data = out.data if isinstance(out.data, dict) else {}
            red_flags.extend(data.get("red_flags") or [])
            green_flags.extend(data.get("green_flags") or [])

        # Closed-source bonus: reward intentionally-private companies that show
        # strong hiring, positive press, and a proven founding team.
        jobs_data = self._data(by_name.get("jobs"))
        news_data = self._data(by_name.get("news"))
        hiring_roles = int(jobs_data.get("total_jobs", 0) or 0)
        news_sentiment = float(news_data.get("sentiment_score", 0.0) or 0.0)
        founder_out = by_name.get("founder")
        founder_score = founder_out.score if founder_out is not None else 0.0

        if (
            hiring_roles > _BONUS_MIN_ROLES
            and news_sentiment > 0
            and founder_score > _BONUS_MIN_FOUNDER_SCORE
        ):
            overall += CLOSED_SOURCE_BONUS
            green_flags.append(
                "Closed-source bonus: strong hiring, positive press, and a "
                f"proven founding team offset limited public code (+{CLOSED_SOURCE_BONUS})"
            )

        overall = max(0.0, min(10.0, overall))  # weights total 1.05 + bonus → clamp

        return MomentumScore(
            **per_agent_scores,
            overall_momentum=round(overall, 2),
            red_flags=red_flags,
            green_flags=green_flags,
        )

    @staticmethod
    def _data(out: AgentOutput | None) -> dict:
        return out.data if (out is not None and isinstance(out.data, dict)) else {}
