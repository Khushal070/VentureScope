from core.models import AgentOutput
from tools.search_tool import fetch_founder_data

PEDIGREE_COMPANIES = {
    "google", "alphabet", "youtube", "deepmind",
    "meta", "facebook", "instagram", "whatsapp",
    "apple", "amazon", "aws", "microsoft", "openai", "anthropic",
    "netflix", "stripe", "airbnb", "uber", "lyft", "tesla", "spacex",
    "nvidia", "linkedin", "twitter", "x corp", "pinterest", "snap",
    "snapchat", "salesforce", "oracle", "ibm", "adobe", "dropbox",
    "palantir", "databricks", "snowflake", "shopify", "square", "block",
    "coinbase", "robinhood", "doordash", "instacart", "twilio",
    "ycombinator", "y combinator",
}
PEDIGREE_SCHOOLS = {
    "stanford", "mit", "harvard", "berkeley", "uc berkeley",
    "carnegie mellon", "cmu", "caltech", "princeton", "yale",
    "columbia", "cornell", "upenn", "wharton", "oxford", "cambridge",
    "iit", "ucla", "uw", "university of washington",
    "georgia tech", "uiuc", "michigan", "northwestern", "chicago",
    "duke", "uc san diego", "ucsd",
}
ADVANCED_DEGREES = {"phd", "ph.d", "doctorate", "mba", "m.b.a", "ms ", "msc ", "master"}


def _hit(text: str, vocab) -> bool:
    t = (text or "").lower()
    return any(v in t for v in vocab)


class FounderAgent:
    agent_name = "founder"

    def run(self, company_name: str, sector: str | None = None) -> AgentOutput:
        try:
            data = fetch_founder_data(company_name)
        except Exception:
            return AgentOutput(
                agent_name=self.agent_name,
                status="failed",
                data=None,
                score=0.0,
                sources=["gemini:gemini-2.5-flash"],
            )

        founders = data.get("founders") or []
        base_score = float(data.get("founder_score", 0.0) or 0.0)
        serial = bool(data.get("serial_entrepreneur", False))

        pedigree_hits = 0
        school_hits = 0
        advanced_degree = False
        prior_exit = False
        domain_experience = False
        sector_l = (sector or "").lower()

        for f in founders:
            prev = " ".join(f.get("previous_companies") or [])
            edu = " ".join(f.get("education") or [])
            bg = f.get("background") or ""

            if _hit(prev, PEDIGREE_COMPANIES) or _hit(bg, PEDIGREE_COMPANIES):
                pedigree_hits += 1
            if _hit(edu, PEDIGREE_SCHOOLS):
                school_hits += 1
            if _hit(edu, ADVANCED_DEGREES) or _hit(bg, ADVANCED_DEGREES):
                advanced_degree = True
            if any(kw in bg.lower() for kw in ("exit", "acquired", "ipo", "sold to")):
                prior_exit = True
            if sector_l and sector_l in (bg + " " + prev).lower():
                domain_experience = True

        score = base_score
        if pedigree_hits:
            score += min(2.0, pedigree_hits * 0.75)
        if school_hits:
            score += min(1.0, school_hits * 0.5)
        if advanced_degree:
            score += 0.5
        if prior_exit:
            score += 1.5
        if serial:
            score += 1.0
        score = round(max(0.0, min(10.0, score)), 2)

        red_flags: list[str] = []
        green_flags: list[str] = []

        if not founders:
            red_flags.append("No founder information could be verified")
        if sector and not domain_experience and founders:
            red_flags.append(f"No clear {sector} domain experience among founders")

        if prior_exit:
            green_flags.append("Founder has a prior successful exit")
        if serial:
            green_flags.append("Serial entrepreneur on the founding team")
        if pedigree_hits:
            green_flags.append(
                f"{pedigree_hits} founder(s) with FAANG / top-startup pedigree"
            )
        if school_hits:
            green_flags.append(f"{school_hits} founder(s) from top-tier institutions")

        sources = ["gemini:gemini-2.5-flash"]

        status = "success" if founders else "failed"

        return AgentOutput(
            agent_name=self.agent_name,
            status=status,
            data={
                **data,
                "pedigree_hits": pedigree_hits,
                "advanced_degree": advanced_degree,
                "prior_exit": prior_exit,
                "red_flags": red_flags,
                "green_flags": green_flags,
            },
            score=score,
            sources=sources,
        )


def run(company_name: str, sector: str | None = None) -> AgentOutput:
    return FounderAgent().run(company_name, sector)
