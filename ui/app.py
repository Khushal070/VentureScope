"""VentureScope — Streamlit front end.

A dark, product-grade dashboard over the LangGraph orchestrator: enter a
company + sector, watch the seven signal agents run, then read the scored
momentum breakdown, the raw source signals, and Gemini's investment verdict.
"""

import asyncio
import concurrent.futures
import os
import re
import sys
import time

# `streamlit run ui/app.py` puts the ui/ dir on sys.path, not the project root,
# so core/agents/tools aren't importable. Prepend the project root (this file's
# parent's parent) so those packages resolve regardless of where it's launched.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core.evaluation import maybe_launch_eval
from core.orchestrator import analyze_company

load_dotenv()

# Kick off the W&B Weave benchmark eval once per process, in the background, so
# it populates the Datasets + Evaluations dashboards without blocking the UI.
maybe_launch_eval()

# --------------------------------------------------------------------------- #
# Palette / constants
# --------------------------------------------------------------------------- #
GREEN = "#1D9E75"
AMBER = "#BA7517"
RED = "#E24B4A"
MUTED = "#7A8290"

AGENTS = [
    ("github", "GitHub", "github_score"),
    ("jobs", "Hiring", "jobs_score"),
    ("news", "News", "news_score"),
    ("patents", "Patents", "patents_score"),
    ("founder", "Founders", "founder_score"),
    ("trends", "Search Trends", "trends_score"),
    ("techstack", "Tech Stack", "techstack_score"),
]

SECTORS = ["AI", "Fintech", "Healthcare", "SaaS", "Consumer", "Other"]

# (name, sector, known outcome) — the hackathon eval set shown to judges.
EVAL_SET = [
    ("Airbnb", "Consumer", "Success"),
    ("Stripe", "Fintech", "Success"),
    ("OpenAI", "AI", "Success"),
    ("Figma", "SaaS", "Success"),
    ("Notion", "SaaS", "Success"),
    ("Zoom", "SaaS", "Success"),
    ("Uber", "Consumer", "Caution"),
    ("Robinhood", "Fintech", "Caution"),
    ("WeWork", "Other", "Failed"),
    ("Theranos", "Healthcare", "Failed"),
]

OUTCOME_COLOR = {"Success": GREEN, "Caution": AMBER, "Failed": RED}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def score_color(score: float) -> str:
    """Green > 7, amber 4-7, red < 4."""
    if score > 7:
        return GREEN
    if score >= 4:
        return AMBER
    return RED


def run_analysis(name: str, sector: str):
    """Blocking entry point executed in a worker thread."""
    return asyncio.run(analyze_company(name, sector))


def outputs_by_name(memo) -> dict:
    return {o.agent_name: o for o in memo.agent_outputs}


def top_flag(data: dict | None, score: float):
    data = data or {}
    greens = data.get("green_flags") or []
    reds = data.get("red_flags") or []
    if score > 7 and greens:
        return GREEN, greens[0]
    if score < 4 and reds:
        return RED, reds[0]
    if greens:
        return GREEN, greens[0]
    if reds:
        return RED, reds[0]
    return MUTED, "No notable signals"


def _md_inline_to_html(text: str) -> str:
    """Convert inline markdown (**bold**, *italic*, `code`) to HTML.

    The verdict often contains markdown emphasis; embedding it in an HTML block
    leaves the markdown unparsed, so we render the emphasis explicitly.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    return text


def score_st_color(score: float) -> str:
    """Streamlit named color for inline colored text (`:color[...]`)."""
    if score > 7:
        return "green"
    if score >= 4:
        return "orange"
    return "red"


def top_flag_native(data: dict | None, score: float):
    """Like top_flag but returns a Streamlit color name instead of hex."""
    data = data or {}
    greens = data.get("green_flags") or []
    reds = data.get("red_flags") or []
    if score > 7 and greens:
        return "green", greens[0]
    if score < 4 and reds:
        return "red", reds[0]
    if greens:
        return "green", greens[0]
    if reds:
        return "red", reds[0]
    return "gray", "No notable signals"


# --------------------------------------------------------------------------- #
# Page config + CSS
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="VentureScope",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    :root {
        --green:#1D9E75; --amber:#BA7517; --red:#E24B4A; --muted:#7A8290;
        --bg:#0B0E14; --panel:#141925; --panel-2:#1A2030; --border:#262E40;
        --text:#E6E9EF; --subtext:#9AA3B2;
    }
    .stApp { background: radial-gradient(1200px 600px at 70% -10%, #16203a 0%, #0B0E14 55%); }
    .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1280px; }

    /* Header */
    .vs-header { display:flex; align-items:baseline; gap:18px; flex-wrap:wrap; }
    .vs-logo { font-size:2.5rem; font-weight:800; letter-spacing:-1px; line-height:1;
        background:linear-gradient(92deg,#2DD4BF 0%,#5B8DEF 60%,#A78BFA 100%);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
    .vs-tagline { color:var(--subtext); font-size:1.02rem; font-weight:400; }
    .vs-divider { border:none; height:1px; margin:1.1rem 0 1.6rem 0;
        background:linear-gradient(90deg,rgba(91,141,239,.55),rgba(167,139,250,.15),transparent); }

    /* Hero score */
    .vs-hero { display:flex; align-items:center; justify-content:space-between;
        background:linear-gradient(180deg,var(--panel) 0%,#10141f 100%);
        border:1px solid var(--border); border-radius:18px; padding:26px 30px; margin-bottom:8px; }
    .vs-hero-label { color:var(--subtext); font-size:.78rem; letter-spacing:2.5px; font-weight:600; }
    .vs-hero-score { font-size:4.6rem; font-weight:800; line-height:1; letter-spacing:-2px; }
    .vs-hero-max { font-size:1.5rem; font-weight:600; color:var(--muted); margin-left:4px; }
    .vs-badge { display:inline-block; padding:10px 20px; border-radius:999px; font-weight:700;
        font-size:1.02rem; border:1px solid transparent; }

    /* Score cards grid */
    .vs-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:6px 0 4px 0; }
    .vs-card { background:var(--panel); border:1px solid var(--border); border-radius:14px;
        padding:16px 16px 14px 16px; transition:transform .12s ease, border-color .12s ease; }
    .vs-card:hover { transform:translateY(-2px); border-color:#3A465E; }
    .vs-card-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
    .vs-card-title { font-size:.82rem; font-weight:600; color:var(--subtext); letter-spacing:.4px; text-transform:uppercase; }
    .vs-card-score { font-size:1.7rem; font-weight:800; line-height:1; }
    .vs-track { height:7px; background:#0c111b; border-radius:6px; overflow:hidden; border:1px solid #1d2535; }
    .vs-fill { height:100%; border-radius:6px; }
    .vs-cardflag { margin-top:11px; font-size:.8rem; color:var(--subtext); display:flex; gap:7px; align-items:flex-start; }
    .vs-dot { width:8px; height:8px; border-radius:50%; margin-top:5px; flex:0 0 auto; }

    /* Flags */
    .vs-flagwrap { display:flex; flex-wrap:wrap; gap:9px; }
    .vs-flag { padding:8px 13px; border-radius:10px; font-size:.86rem; line-height:1.35;
        border:1px solid transparent; }
    .vs-flag-red { background:rgba(226,75,74,.10); border-color:rgba(226,75,74,.35); color:#ff9a99; }
    .vs-flag-green { background:rgba(29,158,117,.10); border-color:rgba(29,158,117,.35); color:#5fe0b0; }

    /* Verdict */
    .vs-verdict { background:linear-gradient(180deg,#15203a 0%,#101626 100%);
        border:1px solid #2c3b63; border-left:4px solid #5B8DEF; border-radius:16px;
        padding:24px 28px; margin-top:4px; box-shadow:0 12px 40px -18px rgba(91,141,239,.5); }
    .vs-verdict-h { font-size:.8rem; letter-spacing:2px; color:#8fb0ff; font-weight:700; margin-bottom:10px; }
    .vs-verdict-body { font-size:1.06rem; line-height:1.72; color:#E6E9EF; }

    /* Progress agents */
    .vs-progress { display:grid; grid-template-columns:repeat(7,1fr); gap:10px; margin:10px 0 6px 0; }
    .vs-agent { background:var(--panel); border:1px solid var(--border); border-radius:12px;
        padding:14px 8px; text-align:center; }
    .vs-agent-name { font-size:.74rem; color:var(--subtext); margin-top:8px; font-weight:600; }
    .vs-agent.done { border-color:rgba(29,158,117,.5); }
    .vs-agent.running { border-color:rgba(91,141,239,.6); }
    .vs-ico { font-size:1.15rem; height:22px; display:flex; align-items:center; justify-content:center; }
    .vs-ico .check { color:var(--green); font-weight:800; }
    .vs-ico .dash { color:var(--muted); }
    .vs-ico .pend { color:#39435a; }
    .spinner { width:16px; height:16px; border:2px solid rgba(91,141,239,.25);
        border-top-color:#5B8DEF; border-radius:50%; animation:spin .7s linear infinite; }
    @keyframes spin { to { transform:rotate(360deg); } }

    /* Section labels */
    .vs-section { font-size:1.05rem; font-weight:700; color:var(--text); margin:26px 0 10px 0;
        display:flex; align-items:center; gap:9px; }
    .vs-section .bar { width:4px; height:18px; border-radius:3px; background:linear-gradient(#5B8DEF,#A78BFA); }

    /* Sidebar eval */
    .ev-row { display:flex; align-items:center; justify-content:space-between;
        padding:9px 11px; border:1px solid var(--border); border-radius:10px;
        background:var(--panel); margin-bottom:7px; }
    .ev-name { font-weight:600; font-size:.9rem; }
    .ev-meta { font-size:.72rem; color:var(--muted); }
    .ev-right { text-align:right; }
    .ev-pred { font-weight:800; font-size:1.05rem; }
    .ev-tag { font-size:.66rem; font-weight:700; padding:2px 8px; border-radius:999px; }

    /* News rows */
    .news-row { padding:11px 0; border-bottom:1px solid var(--border); }
    .news-title a { color:#cdd6e6; text-decoration:none; font-weight:600; }
    .news-title a:hover { color:#8fb0ff; }
    .news-meta { font-size:.76rem; color:var(--muted); margin-top:3px; }
    .sent { font-size:.66rem; font-weight:700; padding:2px 8px; border-radius:999px; margin-right:8px; }

    /* Founder cards */
    .fc { background:var(--panel); border:1px solid var(--border); border-radius:12px;
        padding:15px 17px; margin-bottom:10px; }
    .fc-name { font-weight:700; font-size:1rem; }
    .fc-role { color:#8fb0ff; font-size:.82rem; margin-bottom:6px; }
    .fc-bg { color:var(--subtext); font-size:.88rem; line-height:1.5; }
    .fc-tag { display:inline-block; background:#0e1626; border:1px solid var(--border);
        color:#aeb8c9; font-size:.72rem; padding:3px 9px; border-radius:8px; margin:6px 6px 0 0; }

    .vs-foot { margin-top:34px; padding-top:16px; border-top:1px solid var(--border);
        display:flex; align-items:center; justify-content:space-between; color:var(--muted); font-size:.82rem; }
    .vs-foot a { color:#8fb0ff; text-decoration:none; font-weight:600; }
    div[data-testid="stExpander"] { border:1px solid var(--border); border-radius:12px; background:var(--panel); }
</style>
""",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
st.session_state.setdefault("company_field", "")
st.session_state.setdefault("sector_field", "AI")
st.session_state.setdefault("memo", None)
st.session_state.setdefault("eval_cache", {})  # name.lower() -> overall score


def _load_eval(name: str, sector: str):
    st.session_state.company_field = name
    st.session_state.sector_field = sector
    st.session_state.run_requested = True


# --------------------------------------------------------------------------- #
# Sidebar — eval dataset
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🧪 Eval Dataset")
    st.caption("10 known companies — predicted momentum vs. real-world outcome. Click ▶ to run one.")

    for name, sector, outcome in EVAL_SET:
        pred = st.session_state["eval_cache"].get(name.lower())
        pred_html = (
            f'<span class="ev-pred" style="color:{score_color(pred)}">{pred:.1f}</span>'
            if pred is not None
            else '<span class="ev-meta">—</span>'
        )
        oc = OUTCOME_COLOR[outcome]
        row, btn = st.columns([5, 1])
        with row:
            st.markdown(
                f"""
                <div class="ev-row">
                  <div>
                    <div class="ev-name">{name}</div>
                    <div class="ev-meta">{sector}</div>
                  </div>
                  <div class="ev-right">
                    {pred_html}
                    <div class="ev-tag" style="background:{oc}22;color:{oc};border:1px solid {oc}55;">{outcome}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with btn:
            st.button("▶", key=f"ev_{name}", on_click=_load_eval, args=(name, sector))

    st.caption("Predicted = VentureScope overall momentum (0–10).")


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="vs-header">
      <div class="vs-logo">Venture<span>Scope</span></div>
      <div class="vs-tagline">AI-powered company research for angel investors</div>
    </div>
    <hr class="vs-divider"/>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Input section
# --------------------------------------------------------------------------- #
c1, c2 = st.columns([3, 2])
with c1:
    company = st.text_input(
        "Company name", key="company_field", placeholder="e.g. Stripe, Anthropic, Figma…"
    )
with c2:
    sector = st.selectbox("Sector", SECTORS, key="sector_field")

analyze_clicked = st.button("⚡  Analyze", type="primary", width="content")
run_requested = st.session_state.pop("run_requested", False)
should_run = (analyze_clicked or run_requested) and st.session_state["company_field"].strip()

if (analyze_clicked or run_requested) and not st.session_state["company_field"].strip():
    st.warning("Enter a company name first.")


# --------------------------------------------------------------------------- #
# Run analysis with live agent progress
# --------------------------------------------------------------------------- #
def render_progress(box, statuses: dict):
    cells = []
    for key, label, _f in AGENTS:
        s = statuses.get(key, "pending")
        if s == "running":
            ico = '<div class="spinner"></div>'
        elif s == "done":
            ico = '<span class="check">✓</span>'
        elif s == "empty":
            ico = '<span class="dash">—</span>'
        else:
            ico = '<span class="pend">●</span>'
        cells.append(
            f'<div class="vs-agent {s}"><div class="vs-ico">{ico}</div>'
            f'<div class="vs-agent-name">{label}</div></div>'
        )
    box.markdown(f'<div class="vs-progress">{"".join(cells)}</div>', unsafe_allow_html=True)


if should_run:
    name = st.session_state["company_field"].strip()
    sector_val = st.session_state["sector_field"]

    st.markdown(
        '<div class="vs-section"><span class="bar"></span>Running signal agents</div>',
        unsafe_allow_html=True,
    )
    progress_box = st.empty()
    statuses = {k: "pending" for k, _, _ in AGENTS}
    render_progress(progress_box, statuses)

    error = None
    memo = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(run_analysis, name, sector_val)
            start = time.time()
            # Stagger the "running" reveal so the panel feels alive while we wait.
            while not future.done():
                elapsed = time.time() - start
                for j, (k, _, _) in enumerate(AGENTS):
                    if statuses[k] == "pending" and elapsed > j * 0.45:
                        statuses[k] = "running"
                render_progress(progress_box, statuses)
                time.sleep(0.2)
            memo = future.result()
    except Exception as exc:  # noqa: BLE001
        error = exc

    if error is not None:
        for k in statuses:
            statuses[k] = "empty"
        render_progress(progress_box, statuses)
        st.error(f"Analysis failed: {error}")
    else:
        obn = outputs_by_name(memo)
        for k, _, _ in AGENTS:
            o = obn.get(k)
            statuses[k] = "done" if (o and o.status == "success") else "empty"
        render_progress(progress_box, statuses)
        st.session_state["memo"] = memo
        st.session_state["eval_cache"][name.lower()] = memo.overall_score


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
memo = st.session_state.get("memo")

if memo is None:
    st.info("Enter a company and click **Analyze**, or pick one from the eval set in the sidebar.")
else:
    obn = outputs_by_name(memo)
    m = memo.momentum
    overall = memo.overall_score
    oc = score_color(overall)

    # ---- Hero ----
    st.markdown(
        '<div class="vs-section"><span class="bar"></span>'
        f"Verdict for <span style='color:#8fb0ff'>&nbsp;{memo.company_name}</span>"
        f"<span style='color:var(--muted);font-weight:500'>&nbsp;· {memo.sector or 'unspecified'}</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="vs-hero">
          <div>
            <div class="vs-hero-label">OVERALL MOMENTUM</div>
            <div class="vs-hero-score" style="color:{oc}">{overall:.1f}<span class="vs-hero-max">/10</span></div>
          </div>
          <div>
            <span class="vs-badge" style="background:{oc}1f;color:{oc};border-color:{oc}66;">{memo.recommendation}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Score cards ----
    st.markdown(
        '<div class="vs-section"><span class="bar"></span>Signal breakdown</div>',
        unsafe_allow_html=True,
    )
    items = [(label, float(getattr(m, field)), key) for key, label, field in AGENTS]
    per_row = 4
    for i in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for col, (label, sc, key) in zip(cols, items[i : i + per_row]):
            with col:
                data = (
                    obn[key].data
                    if (key in obn and isinstance(obn[key].data, dict))
                    else {}
                )
                fcolor, flag = top_flag_native(data, sc)
                st.metric(label, f"{sc:.1f} / 10")
                st.progress(min(1.0, max(0.0, sc / 10.0)))
                st.markdown(f":{fcolor}[{flag}]")

    # ---- Raw signals ----
    st.markdown(
        '<div class="vs-section"><span class="bar"></span>Raw signals</div>',
        unsafe_allow_html=True,
    )

    def gd(key: str) -> dict:
        o = obn.get(key)
        return o.data if (o and isinstance(o.data, dict)) else {}

    # Hiring
    jd = gd("jobs")
    with st.expander(f"💼  Hiring  —  {jd.get('total_jobs', 0)} open roles", expanded=False):
        depts = jd.get("jobs_by_department") or {}
        mc = st.columns(4)
        mc[0].metric("Engineering", depts.get("engineering", 0))
        mc[1].metric("Product", depts.get("product", 0))
        mc[2].metric("Sales", depts.get("sales", 0))
        mc[3].metric("Hiring velocity", f"{jd.get('hiring_velocity', 0)}")
        postings = jd.get("recent_postings") or []
        if postings:
            df = pd.DataFrame(postings)
            if "date" in df:
                df["date"] = df["date"].astype(str).str.slice(0, 10)
            st.dataframe(
                df.rename(columns={"title": "Title", "date": "Posted", "location": "Location"}),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No job postings returned.")

    # GitHub
    ghd = gd("github")
    with st.expander(f"💻  GitHub  —  {ghd.get('org_name') or 'no org found'}", expanded=False):
        mc = st.columns(3)
        mc[0].metric("Commits (30d)", ghd.get("total_commits_30d", 0))
        mc[1].metric("Contributors", ghd.get("contributor_count", 0))
        mc[2].metric("Total stars", f"{ghd.get('stars_total', 0):,}")
        repos = ghd.get("top_repos") or []
        if repos:
            df = pd.DataFrame(repos)
            keep = [c for c in ["name", "primary_language", "stars", "forks", "open_issues", "commits_30d"] if c in df]
            st.dataframe(
                df[keep].rename(columns={
                    "name": "Repo", "primary_language": "Language", "stars": "Stars",
                    "forks": "Forks", "open_issues": "Issues", "commits_30d": "Commits 30d"}),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No public repositories found.")

    # News
    nd = gd("news")
    with st.expander(f"📰  News  —  {nd.get('total_articles', 0)} articles (30d)", expanded=False):
        mc = st.columns(3)
        mc[0].metric("Positive", nd.get("positive_count", 0))
        mc[1].metric("Negative", nd.get("negative_count", 0))
        mc[2].metric("Sentiment", f"{nd.get('sentiment_score', 0):+.2f}")
        arts = nd.get("top_articles") or []
        if arts:
            for a in arts[:12]:
                sentiment = a.get("sentiment", "neutral")
                scol = {"positive": GREEN, "negative": RED}.get(sentiment, MUTED)
                url = a.get("url") or "#"
                title = a.get("title") or "(untitled)"
                st.markdown(
                    f"""
                    <div class="news-row">
                      <div class="news-title"><a href="{url}" target="_blank">{title}</a></div>
                      <div class="news-meta">
                        <span class="sent" style="background:{scol}22;color:{scol};">{sentiment.upper()}</span>
                        {a.get('source','')} · {str(a.get('date',''))[:10]}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No recent coverage found.")

    # Patents
    pd_ = gd("patents")
    with st.expander(f"📜  Patents  —  {pd_.get('total_patents', 0)} filed", expanded=False):
        mc = st.columns(2)
        mc[0].metric("Total patents", pd_.get("total_patents", 0))
        mc[1].metric("Filed last 12 mo", pd_.get("patent_velocity", 0))
        pats = pd_.get("recent_patents") or []
        if pats:
            df = pd.DataFrame(pats)
            df["link"] = df.get("url", "")
            show = df[[c for c in ["patent_number", "title", "date", "link"] if c in df]]
            st.dataframe(
                show.rename(columns={"patent_number": "Patent #", "title": "Title", "date": "Filed", "link": "USPTO"}),
                width="stretch", hide_index=True,
                column_config={"USPTO": st.column_config.LinkColumn("USPTO", display_text="View")},
            )
        else:
            st.caption("No patents found under this assignee.")

    # Founders
    fd = gd("founder")
    founders = fd.get("founders") or []
    with st.expander(f"👤  Founders  —  {len(founders)} identified", expanded=False):
        if founders:
            for f in founders:
                prevs = "".join(f'<span class="fc-tag">🏢 {c}</span>' for c in (f.get("previous_companies") or []))
                edus = "".join(f'<span class="fc-tag">🎓 {e}</span>' for e in (f.get("education") or []))
                st.markdown(
                    f"""
                    <div class="fc">
                      <div class="fc-name">{f.get('name','Unknown')}</div>
                      <div class="fc-role">{f.get('role','')}</div>
                      <div class="fc-bg">{f.get('background','')}</div>
                      <div>{prevs}{edus}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No founder information could be verified.")

    # Trends
    td = gd("trends")
    with st.expander(
        f"📈  Search Trends  —  {td.get('trend_direction', 'n/a')} (interest {td.get('current_interest', 0)})",
        expanded=False,
    ):
        mc = st.columns(3)
        mc[0].metric("Current", td.get("current_interest", 0))
        mc[1].metric("12-mo avg", td.get("avg_interest", 0))
        mc[2].metric("Peak", td.get("peak_interest", 0))
        monthly = td.get("monthly_data") or []
        if monthly:
            mdf = pd.DataFrame(monthly)
            if {"date", "interest"}.issubset(mdf.columns):
                mdf = mdf.set_index("date")
                st.line_chart(mdf["interest"], color=GREEN, height=220)
        else:
            st.caption("No Google Trends data available.")

    # Tech stack
    tsd = gd("techstack")
    with st.expander(
        f"🧱  Tech Stack  —  primary: {tsd.get('primary_language') or 'unknown'}",
        expanded=False,
    ):
        langs = tsd.get("languages") or {}
        cats = tsd.get("tech_categories") or {}
        if langs:
            ldf = pd.DataFrame({"% of code": langs}).sort_values("% of code", ascending=False).head(10)
            st.bar_chart(ldf, color=GREEN, height=240)
        else:
            st.caption("No language data detected.")
        if cats:
            cc = st.columns(4)
            cc[0].metric("Frontend", f"{cats.get('frontend', 0):.0f}%")
            cc[1].metric("Backend", f"{cats.get('backend', 0):.0f}%")
            cc[2].metric("ML / AI", f"{cats.get('ml', 0):.0f}%")
            cc[3].metric("DevOps", f"{cats.get('devops', 0):.0f}%")

    # ---- Flags ----
    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown(
            '<div class="vs-section"><span class="bar" style="background:#E24B4A"></span>Red flags</div>',
            unsafe_allow_html=True,
        )
        reds = m.red_flags or []
        if reds:
            st.markdown(
                '<div class="vs-flagwrap">'
                + "".join(f'<div class="vs-flag vs-flag-red">⚠ {r}</div>' for r in reds)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("No red flags detected.")
    with fc2:
        st.markdown(
            '<div class="vs-section"><span class="bar" style="background:#1D9E75"></span>Green flags</div>',
            unsafe_allow_html=True,
        )
        greens = m.green_flags or []
        if greens:
            st.markdown(
                '<div class="vs-flagwrap">'
                + "".join(f'<div class="vs-flag vs-flag-green">✓ {g}</div>' for g in greens)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("No green flags detected.")

    # ---- Gemini verdict ----
    st.markdown(
        '<div class="vs-section"><span class="bar"></span>Gemini investment verdict</div>',
        unsafe_allow_html=True,
    )
    verdict = (memo.claude_verdict or "").strip()
    if verdict:
        st.markdown(
            f'<div class="vs-verdict">'
            f'<div class="vs-verdict-h">◆ PARTNER MEMO</div>'
            f'<div class="vs-verdict-body">{_md_inline_to_html(verdict)}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Verdict unavailable (Gemini reasoning step did not return text).")

    # ---- Footer: Weave trace ----
    entity = os.getenv("WANDB_ENTITY")
    weave_url = (
        f"https://wandb.ai/{entity}/venturescope/weave" if entity else "https://wandb.ai/home"
    )
    st.markdown(
        f"""
        <div class="vs-foot">
          <span>VentureScope · 7 parallel agents · scored via weighted MomentumScore</span>
          <span>🔭 <a href="{weave_url}" target="_blank">View full trace in W&amp;B Weave</a> &nbsp;·&nbsp; project <code>venturescope</code></span>
        </div>
        """,
        unsafe_allow_html=True,
    )
