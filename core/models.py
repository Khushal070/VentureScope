from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class GitHubSignal(BaseModel):
    repo_full_name: Optional[str] = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    commits_last_30d: int = 0
    contributors_last_30d: int = 0
    star_velocity_30d: float = 0.0
    primary_language: Optional[str] = None
    last_commit_at: Optional[datetime] = None
    topics: list[str] = Field(default_factory=list)


class JobsSignal(BaseModel):
    company: Optional[str] = None
    open_roles: int = 0
    engineering_roles: int = 0
    leadership_roles: int = 0
    locations: list[str] = Field(default_factory=list)
    role_titles: list[str] = Field(default_factory=list)
    hiring_velocity_30d: float = 0.0


class NewsSignal(BaseModel):
    article_count_30d: int = 0
    avg_sentiment: float = 0.0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    top_headlines: list[str] = Field(default_factory=list)
    top_sources: list[str] = Field(default_factory=list)


class PatentsSignal(BaseModel):
    total_patents: int = 0
    patents_last_3y: int = 0
    patent_titles: list[str] = Field(default_factory=list)
    classifications: list[str] = Field(default_factory=list)
    most_recent_filing: Optional[datetime] = None


class FounderSignal(BaseModel):
    founders: list[str] = Field(default_factory=list)
    prior_exits: int = 0
    prior_companies: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    years_experience: Optional[int] = None
    notable_affiliations: list[str] = Field(default_factory=list)


class TrendsSignal(BaseModel):
    keyword: Optional[str] = None
    interest_avg_12mo: float = 0.0
    interest_change_pct_90d: float = 0.0
    related_queries_rising: list[str] = Field(default_factory=list)
    related_topics_rising: list[str] = Field(default_factory=list)


class TechStackSignal(BaseModel):
    detected_frameworks: list[str] = Field(default_factory=list)
    detected_languages: list[str] = Field(default_factory=list)
    detected_cloud: list[str] = Field(default_factory=list)
    detected_analytics: list[str] = Field(default_factory=list)
    ai_ml_indicators: list[str] = Field(default_factory=list)
    modernity_indicators: list[str] = Field(default_factory=list)


class MomentumScore(BaseModel):
    github_score: float = Field(0.0, ge=0.0, le=10.0)
    jobs_score: float = Field(0.0, ge=0.0, le=10.0)
    news_score: float = Field(0.0, ge=0.0, le=10.0)
    patents_score: float = Field(0.0, ge=0.0, le=10.0)
    founder_score: float = Field(0.0, ge=0.0, le=10.0)
    trends_score: float = Field(0.0, ge=0.0, le=10.0)
    techstack_score: float = Field(0.0, ge=0.0, le=10.0)
    overall_momentum: float = Field(0.0, ge=0.0, le=10.0)
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)


class AgentOutput(BaseModel):
    agent_name: str
    status: str
    data: Optional[Any] = None
    score: float = Field(0.0, ge=0.0, le=10.0)
    sources: list[str] = Field(default_factory=list)


class FinalMemo(BaseModel):
    company_name: str
    sector: Optional[str] = None
    overall_score: float = Field(0.0, ge=0.0, le=10.0)
    momentum: MomentumScore
    agent_outputs: list[AgentOutput] = Field(default_factory=list)
    claude_verdict: str = ""
    recommendation: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
