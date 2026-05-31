"""LangGraph orchestrator for VentureScope.

Fans out to all seven signal agents in parallel (via the LangGraph ``Send``
API), aggregates their outputs into a :class:`MomentumScore`, asks Google
Gemini to write an investment verdict, and assembles the final
:class:`FinalMemo`.

Every Gemini API call and every agent invocation is wrapped with
``weave.op()`` so the full run is traced in W&B Weave.
"""

from __future__ import annotations

import operator
import os
from typing import Annotated, Optional, TypedDict

import weave
from google import genai
from google.genai import types
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agents import (
    founder_agent,
    github_agent,
    jobs_agent,
    news_agent,
    patents_agent,
    techstack_agent,
    trends_agent,
)
from core.models import AgentOutput, FinalMemo, MomentumScore
from core.scorer import MomentumScorer

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Module-level: each agent exposes a `run(company_name, sector) -> AgentOutput`.
AGENT_RUNNERS = {
    "github": github_agent.run,
    "jobs": jobs_agent.run,
    "news": news_agent.run,
    "patents": patents_agent.run,
    "founder": founder_agent.run,
    "trends": trends_agent.run,
    "techstack": techstack_agent.run,
}

# Frozen system prompt — kept byte-stable so it can be prompt-cached across runs.
_VERDICT_SYSTEM = (
    "You are a seasoned early-stage venture investor writing a crisp internal "
    "investment verdict for a partner meeting. You are given a structured "
    "MomentumScore: seven 0-10 sub-scores (github, jobs, news, patents, "
    "founder, trends, techstack), a weighted overall_momentum, and aggregated "
    "red_flags and green_flags drawn from automated signal analysis.\n\n"
    "Write a single verdict of 150-200 words that interprets these signals as "
    "a whole rather than restating the numbers. You MUST:\n"
    "  - Open with a one-line stance (e.g. lean-in, watch, or pass) justified "
    "by the overall momentum.\n"
    "  - Identify the single most important OPPORTUNITY the signals reveal.\n"
    "  - Identify the single most important RISK the signals reveal.\n"
    "  - Note any tension between strong and weak signals.\n"
    "Be concrete and decisive. Do not use headers, bullet lists, or preamble — "
    "return only the verdict prose."
)

_scorer = MomentumScorer()
_weave_initialized = False


def _ensure_weave() -> None:
    """Initialize Weave once per process for tracing."""
    global _weave_initialized
    if not _weave_initialized:
        weave.init("venturescope")
        _weave_initialized = True


class VentureScopeState(TypedDict):
    """Shared graph state. ``agent_outputs`` uses an additive reducer so the
    seven parallel agent nodes can each append their result concurrently."""

    company_name: str
    sector: Optional[str]
    agent_outputs: Annotated[list[AgentOutput], operator.add]
    momentum_score: Optional[MomentumScore]
    verdict: str
    final_memo: Optional[FinalMemo]
    status: str


class _AgentTask(TypedDict):
    """Payload delivered to an agent node via the Send API."""

    agent_name: str
    company_name: str
    sector: Optional[str]


def _dispatch_agents(state: VentureScopeState) -> list[Send]:
    """START fan-out: emit one Send per agent so all seven run in parallel."""
    return [
        Send(
            "run_agent",
            {
                "agent_name": name,
                "company_name": state["company_name"],
                "sector": state.get("sector"),
            },
        )
        for name in AGENT_RUNNERS
    ]


@weave.op()
def run_agent(state: _AgentTask) -> dict:
    """Run a single signal agent. Wrapped with weave.op() for tracing."""
    name = state["agent_name"]
    runner = AGENT_RUNNERS[name]
    try:
        output = runner(state["company_name"], state.get("sector"))
    except Exception as exc:  # never let one agent fail the whole graph
        output = AgentOutput(
            agent_name=name,
            status="failed",
            data={"error": str(exc), "red_flags": [], "green_flags": []},
            score=0.0,
        )
    return {"agent_outputs": [output]}


def aggregate(state: VentureScopeState) -> dict:
    """Barrier node: runs once all seven agents have reported. Scores them."""
    momentum = _scorer.score(state["agent_outputs"])
    return {"momentum_score": momentum, "status": "scored"}


_SIGNAL_LABELS = {
    "github_score": "engineering output (GitHub)",
    "jobs_score": "hiring",
    "news_score": "media sentiment",
    "patents_score": "IP / patents",
    "founder_score": "founding team",
    "trends_score": "search demand",
    "techstack_score": "tech stack",
}


def _response_text(response) -> str:
    """Extract text from a Gemini response, tolerating empty/blocked candidates."""
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


def _rule_based_verdict(
    momentum: MomentumScore, company_name: str, sector: Optional[str]
) -> str:
    """Deterministic fallback verdict built straight from the scores.

    Used when Gemini is unavailable so the memo is never blank.
    """
    overall = momentum.overall_momentum
    subs = {k: getattr(momentum, k) for k in _SIGNAL_LABELS}
    strongest_k = max(subs, key=subs.get)
    weakest_k = min(subs, key=subs.get)
    strongest = _SIGNAL_LABELS[strongest_k]
    weakest = _SIGNAL_LABELS[weakest_k]

    if overall > 7:
        stance = f"Lean in. {company_name} shows strong momentum"
    elif overall >= 4:
        stance = f"Watch closely. {company_name} shows mixed but real momentum"
    else:
        stance = f"Pass for now. {company_name} shows weak momentum"

    opportunity = (
        momentum.green_flags[0]
        if momentum.green_flags
        else f"its strongest signal is {strongest} ({subs[strongest_k]:.1f}/10)"
    )
    risk = (
        momentum.red_flags[0]
        if momentum.red_flags
        else f"its weakest signal is {weakest} ({subs[weakest_k]:.1f}/10)"
    )

    sector_txt = f" in the {sector} space" if sector else ""
    return (
        f"{stance}{sector_txt}, with an overall momentum score of "
        f"{overall:.1f}/10. The clearest strength is {strongest} "
        f"({subs[strongest_k]:.1f}/10), while {weakest} ({subs[weakest_k]:.1f}/10) "
        f"is the laggard and bears watching. The most important opportunity: "
        f"{opportunity}. The most important risk: {risk}. On balance, the signal "
        f"mix points to a {'high' if overall > 7 else 'moderate' if overall >= 4 else 'low'}"
        f"-conviction profile that warrants "
        f"{'deeper diligence' if overall >= 4 else 'caution'} before committing."
    )


@weave.op()
async def generate_verdict(
    momentum: MomentumScore, company_name: str, sector: Optional[str]
) -> str:
    """Interpret the MomentumScore into an investment verdict via Gemini.

    Retries the Gemini call, and if it fails or returns empty, falls back to a
    deterministic rule-based verdict so the result is never blank. Wrapped with
    weave.op() so the prompt, model, and response are traced.
    """
    if GEMINI_API_KEY:
        user_payload = (
            f"Company: {company_name}\n"
            f"Sector: {sector or 'unspecified'}\n\n"
            f"MomentumScore JSON:\n{momentum.model_dump_json(indent=2)}"
        )
        for attempt in range(2):  # one retry on transient failure / empty text
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = await client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=user_payload,
                    config=types.GenerateContentConfig(
                        system_instruction=_VERDICT_SYSTEM,
                        temperature=0.4,
                        max_output_tokens=1024,
                        # gemini-2.5-flash is a thinking model; disable thinking
                        # so the budget produces the verdict, not reasoning.
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                text = _response_text(response)
                if text:
                    return text
            except Exception:
                pass

    # Gemini unavailable, exhausted, or empty → deterministic fallback.
    return _rule_based_verdict(momentum, company_name, sector)


def _recommendation(overall: float) -> str:
    if overall >= 7.5:
        return "Strong Buy — high momentum across signals"
    if overall >= 6.0:
        return "Buy — solid momentum"
    if overall >= 4.0:
        return "Watch — mixed signals"
    return "Pass — weak momentum"


async def reason(state: VentureScopeState) -> dict:
    """Gemini reasoning node: produces the natural-language verdict."""
    momentum = state["momentum_score"]
    assert momentum is not None
    verdict = await generate_verdict(
        momentum, state["company_name"], state.get("sector")
    )
    return {"status": "reasoned", "verdict": verdict}


def write_memo(state: VentureScopeState) -> dict:
    """Assemble the final FinalMemo pydantic object."""
    momentum = state["momentum_score"]
    assert momentum is not None
    verdict = state.get("verdict", "")

    memo = FinalMemo(
        company_name=state["company_name"],
        sector=state.get("sector"),
        overall_score=momentum.overall_momentum,
        momentum=momentum,
        agent_outputs=state["agent_outputs"],
        claude_verdict=verdict,
        recommendation=_recommendation(momentum.overall_momentum),
    )
    return {"final_memo": memo, "status": "complete"}


def build_graph():
    """Construct the VentureScope StateGraph.

    START ──(Send × 7)──▶ run_agent ──▶ aggregate ──▶ reason ──▶ write_memo ──▶ END
    """
    builder = StateGraph(VentureScopeState)

    builder.add_node("run_agent", run_agent)
    builder.add_node("aggregate", aggregate)
    builder.add_node("reason", reason)
    builder.add_node("write_memo", write_memo)

    # START fans out to all seven agents in parallel via the Send API.
    builder.add_conditional_edges(START, _dispatch_agents, ["run_agent"])
    # Every agent node feeds the aggregator; it waits for all seven.
    builder.add_edge("run_agent", "aggregate")
    builder.add_edge("aggregate", "reason")
    builder.add_edge("reason", "write_memo")
    builder.add_edge("write_memo", END)

    return builder.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def analyze_company(company_name: str, sector: str) -> FinalMemo:
    """Run the full VentureScope pipeline for one company and return the memo."""
    _ensure_weave()
    result = await _get_graph().ainvoke(
        {
            "company_name": company_name,
            "sector": sector,
            "agent_outputs": [],
            "momentum_score": None,
            "verdict": "",
            "final_memo": None,
            "status": "started",
        }
    )
    memo = result["final_memo"]
    assert memo is not None
    return memo


class Orchestrator:
    """Thin synchronous wrapper kept for the existing ``main.py`` entry point."""

    def run(self, company_name: str, sector: str | None = None) -> FinalMemo:
        import asyncio

        return asyncio.run(analyze_company(company_name, sector or ""))
