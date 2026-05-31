"""VentureScope CLI entry point.

Usage:
    python main.py "Perplexity AI" "AI Search"
    python main.py "Stripe"            # sector optional

Loads environment variables, initializes W&B Weave tracing, runs the full
seven-agent analysis pipeline, and prints the resulting FinalMemo as JSON.

Importing this module has no side effects (analysis only runs under
``if __name__ == "__main__"``), so it is safe to import from the Streamlit UI
or anywhere else.
"""

import argparse
import asyncio

import weave
from dotenv import load_dotenv

from core.models import FinalMemo
from core.orchestrator import analyze_company


def run(company_name: str, sector: str = "") -> FinalMemo:
    """Synchronous helper: run the pipeline and return the FinalMemo."""
    return asyncio.run(analyze_company(company_name, sector))


def main() -> None:
    load_dotenv()
    weave.init("venturescope")

    parser = argparse.ArgumentParser(
        prog="venturescope",
        description="AI-powered company research for angel investors.",
    )
    parser.add_argument("company", help="Company name to research")
    parser.add_argument(
        "sector",
        nargs="?",
        default="",
        help="Sector / market (optional), e.g. 'AI Search'",
    )
    args = parser.parse_args()

    memo = asyncio.run(analyze_company(args.company, args.sector))
    print(memo.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
