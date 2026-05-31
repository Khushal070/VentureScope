"""W&B Weave evaluation for VentureScope.

On app startup (in a background thread) this:

1. Runs the full pipeline for 10 benchmark companies and publishes a
   ``weave.Dataset`` named ``eval_benchmark`` containing each company's inputs
   (name, sector, expected_outcome) plus its analysis results (overall + per-
   agent scores, flag counts, recommendation).
2. Runs a ``weave.Evaluation`` that maps VentureScope's recommendation to an
   outcome label and scores it against the expected outcome, logging accuracy
   to the Weave dashboard (Datasets + Evaluations sections).

Everything is best-effort and exception-safe so it can never break the UI.
"""

import asyncio
import os
import threading

import weave

from core.orchestrator import analyze_company

# (company, sector, expected real-world outcome)
EVAL_COMPANIES = [
    {"company_name": "Airbnb", "sector": "Consumer", "expected_outcome": "Success"},
    {"company_name": "Stripe", "sector": "Fintech", "expected_outcome": "Success"},
    {"company_name": "OpenAI", "sector": "AI", "expected_outcome": "Success"},
    {"company_name": "Figma", "sector": "SaaS", "expected_outcome": "Success"},
    {"company_name": "Notion", "sector": "SaaS", "expected_outcome": "Success"},
    {"company_name": "Zoom", "sector": "SaaS", "expected_outcome": "Success"},
    {"company_name": "Uber", "sector": "Consumer", "expected_outcome": "Caution"},
    {"company_name": "Robinhood", "sector": "Fintech", "expected_outcome": "Caution"},
    {"company_name": "WeWork", "sector": "Other", "expected_outcome": "Failed"},
    {"company_name": "Theranos", "sector": "Healthcare", "expected_outcome": "Failed"},
]

# Filled during dataset construction; the evaluation model reads from it so the
# pipeline only runs once per company (not again during evaluate()).
_RESULTS: dict[str, dict] = {}

_started = False
_lock = threading.Lock()


def recommendation_to_outcome(recommendation: str) -> str:
    """Map a VentureScope recommendation string to an outcome label.

    "Strong Buy"/"Buy" -> Success, "Watch" -> Caution, "Pass" -> Failed.
    """
    r = (recommendation or "").lower()
    if "pass" in r:
        return "Failed"
    if "watch" in r:
        return "Caution"
    if "buy" in r:  # covers "buy" and "strong buy"
        return "Success"
    return "Caution"


@weave.op()
def venturescope_recommender(company_name: str, sector: str) -> dict:
    """Evaluation model: return VentureScope's prediction for a company.

    Reads the precomputed result so the pipeline isn't re-run during evaluate().
    """
    res = _RESULTS.get(company_name)
    if not res:
        return {
            "recommendation": "Unknown",
            "predicted_outcome": "Caution",
            "overall_score": 0.0,
        }
    return res


@weave.op()
def outcome_match_scorer(expected_outcome: str, output: dict) -> dict:
    """Score whether the predicted outcome matches the expected outcome."""
    predicted = (output or {}).get("predicted_outcome")
    return {"correct": bool(predicted == expected_outcome)}


def _analyze_to_row(company: dict) -> dict:
    """Run the pipeline for one company and build its benchmark row."""
    name, sector = company["company_name"], company["sector"]
    try:
        memo = asyncio.run(analyze_company(name, sector))
    except Exception:
        memo = None

    if memo is None:
        _RESULTS[name] = {
            "recommendation": "Unknown",
            "predicted_outcome": "Caution",
            "overall_score": 0.0,
        }
        return {
            **company,
            "overall_score": 0.0,
            "github": 0.0, "hiring": 0.0, "news": 0.0, "patents": 0.0,
            "founders": 0.0, "trends": 0.0, "techstack": 0.0,
            "red_flag_count": 0, "green_flag_count": 0,
            "recommendation": "Unknown",
        }

    m = memo.momentum
    rec = memo.recommendation
    _RESULTS[name] = {
        "recommendation": rec,
        "predicted_outcome": recommendation_to_outcome(rec),
        "overall_score": round(memo.overall_score, 2),
    }
    return {
        **company,
        "overall_score": round(memo.overall_score, 2),
        "github": m.github_score,
        "hiring": m.jobs_score,
        "news": m.news_score,
        "patents": m.patents_score,
        "founders": m.founder_score,
        "trends": m.trends_score,
        "techstack": m.techstack_score,
        "red_flag_count": len(m.red_flags),
        "green_flag_count": len(m.green_flags),
        "recommendation": rec,
    }


def run_eval() -> None:
    """Build + publish the dataset, then run + log the evaluation."""
    weave.init("venturescope")

    rows = [_analyze_to_row(c) for c in EVAL_COMPANIES]

    dataset = weave.Dataset(name="eval_benchmark", rows=rows)
    weave.publish(dataset, name="eval_benchmark")

    evaluation = weave.Evaluation(
        name="venturescope_benchmark",
        dataset=dataset,
        scorers=[outcome_match_scorer],
    )
    asyncio.run(evaluation.evaluate(venturescope_recommender))


def _safe_run() -> None:
    try:
        run_eval()
    except Exception as exc:  # never crash the app
        print(f"[venturescope-eval] skipped: {type(exc).__name__}: {exc}")


def maybe_launch_eval() -> bool:
    """Launch the eval once per process in a daemon thread (non-blocking).

    Returns True if it started the run, False if skipped/already running. Set
    ``VENTURESCOPE_SKIP_EVAL=1`` to disable (e.g. in tests).
    """
    global _started
    if os.getenv("VENTURESCOPE_SKIP_EVAL"):
        return False
    with _lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_safe_run, name="venturescope-eval", daemon=True).start()
    return True
