# VentureScope

### [Live Demo -> khushaltrivedi-venturescope.streamlit.app](https://khushaltrivedi-venturescope.streamlit.app)

**AI-powered company research for angel investors.**

VentureScope analyzes a company across **seven independent signal domains** in parallel, scores its overall **momentum** with a weighted model, and uses **Gemini 2.5 Flash** to write a concise, partner-ready investment verdict - all traced end-to-end in **Weights & Biases Weave**.

Point it at a company name and sector, and in one pass it tells you: *is this company gaining momentum, what's the biggest opportunity, and what's the biggest risk?*

---

## What it does

```
                 +----------------------------------------------+
   START ------> |  7 signal agents run IN PARALLEL (Send API)  |
                 |  github - jobs - news - patents - founder -   |
                 |  trends - techstack                           |
                 +----------------------+------------------------+
                                        |
                         Aggregator -> MomentumScorer
                         (weighted 0-10 overall score + flags)
                                        |
                         Gemini 2.5 Flash reasoning node
                         -> 150-200 word investment verdict
                                        |
                         FinalMemo -> CLI JSON / Streamlit UI
```

- **7 agents, truly parallel** - fanned out via LangGraph's `Send` API, not run sequentially
- **Weighted MomentumScore** - hiring 20%, news 20%, founders 20%, github 15%, patents 10%, trends 10%, techstack 5%
- **Aggregated red/green flags** collected from every agent
- **Gemini 2.5 Flash investment verdict** interpreting the signals as a whole
- **Full tracing** - every agent call and LLM call is wrapped with `weave.op()` and logged to the `venturescope` Weave project
- **Polished Streamlit dashboard** - live agent progress, score breakdown, expandable raw-signal drill-downs, and an eval dataset of 10 known companies

---

## The seven agents

| Agent | Signal | Source | What it measures |
|---|---|---|---|
| **GitHub** | Engineering velocity | GitHub API | Commit volume and growth, contributors, stars across top repos |
| **Hiring** | Growth posture | Adzuna Jobs API | Open roles, engineering vs sales mix, hiring velocity |
| **News** | Market narrative | NewsAPI | Article volume, sentiment, funding/lawsuit keyword signals |
| **Patents** | IP moat | PatentsView (USPTO) | Total patents, recent filing velocity |
| **Founders** | Team quality | Gemini + Wikipedia | Pedigree (FAANG/top-startup), prior exits, education, serial founders |
| **Search Trends** | Demand signal | Google Trends (pytrends) | 12-month interest, direction (rising/falling), peak |
| **Tech Stack** | Engineering modernity | GitHub languages | Modern vs legacy languages, ML/AI presence, repo traction |

Each agent returns an `AgentOutput` with a 0-10 `score`, the raw `data`, and its own `red_flags` / `green_flags`. Agents **never raise** - on any failure they return a safe, empty result so one dead API cannot break the run.

---

## Tech stack

- **Orchestration:** [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` with the `Send` API for parallel fan-out
- **LLM:** [Gemini 2.5 Flash](https://aistudio.google.com/) via the `google-genai` Python SDK
- **Observability:** [W&B Weave](https://weave-docs.wandb.ai/) (`weave.op()` tracing)
- **Data model:** [Pydantic](https://docs.pydantic.dev/) v2
- **UI:** [Streamlit](https://streamlit.io/) (dark theme, custom CSS) + pandas charts
- **Data sources:** GitHub API, Adzuna, NewsAPI, PatentsView, Google Trends (pytrends)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/Khushal070/VentureScope
cd VentureScope

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Create a `.env` file in the project root:

```
GEMINI_API_KEY=...           # https://aistudio.google.com/  (LLM verdict + founder research)
WANDB_API_KEY=...            # https://wandb.ai/             (W&B Weave tracing)
ADZUNA_APP_ID=...            # https://developer.adzuna.com/ (Hiring agent)
ADZUNA_APP_KEY=...
NEWSAPI_KEY=...              # https://newsapi.org/           (News agent)
GITHUB_TOKEN=ghp_...         # optional - raises GitHub rate limits
```

> **Graceful degradation:** any missing key simply makes that one agent return "no data" - the rest of the pipeline still runs.

---

## How to run

### Streamlit dashboard

```bash
streamlit run ui/app.py
```

Open the local URL, enter a company and sector, and hit **Analyze** - or pick one of the 10 companies from the eval dataset in the sidebar.

### Command line

```bash
python main.py "Perplexity AI" "AI Search"
python main.py "Stripe"
```

Prints the full `FinalMemo` as formatted JSON and logs the trace to Weave.

### As a library

```python
import asyncio
from core.orchestrator import analyze_company

memo = asyncio.run(analyze_company("Figma", "SaaS"))
print(memo.overall_score, memo.recommendation)
print(memo.claude_verdict)
```

---

## Project structure

```
VentureScope/
├── main.py                  # CLI entry point
├── core/
│   ├── models.py            # Pydantic models: AgentOutput, MomentumScore, FinalMemo
│   ├── orchestrator.py      # LangGraph StateGraph: parallel fan-out -> score -> verdict -> memo
│   └── scorer.py            # MomentumScorer (weighted aggregation + flag collection)
├── agents/                  # One agent per signal; each exposes run(company, sector)
│   ├── github_agent.py
│   ├── jobs_agent.py
│   ├── news_agent.py
│   ├── patents_agent.py
│   ├── founder_agent.py
│   ├── trends_agent.py
│   └── techstack_agent.py
├── tools/                   # Thin API clients with safe-default error handling
│   ├── github_tool.py
│   ├── adzuna_tool.py
│   ├── newsapi_tool.py
│   ├── uspto_tool.py
│   ├── search_tool.py
│   ├── trends_tool.py
│   └── techstack_tool.py
├── ui/
│   └── app.py               # Streamlit dashboard
├── requirements.txt
└── .env                     # API keys (not committed)
```

---

## Scoring model

`overall_momentum` is the weighted sum of the seven 0-10 sub-scores:

| Signal | Weight |
|---|---:|
| Hiring | 20% |
| News | 20% |
| Founders | 20% |
| GitHub | 15% |
| Patents | 10% |
| Search Trends | 10% |
| Tech Stack | 5% |

The Streamlit UI color-codes scores: **green > 7**, **amber 4-7**, **red < 4**.

---

## Eval dataset

The sidebar ships with 10 well-known companies labeled by real-world outcome (**Success / Caution / Failed**) - Airbnb, Stripe, OpenAI, Figma, Notion, Zoom, Uber, Robinhood, WeWork, Theranos - so judges can sanity-check predicted momentum against known ground truth.

---

## License

Built for the Multi-Agent Orchestration Build Day hackathon. Use at your own discretion.
