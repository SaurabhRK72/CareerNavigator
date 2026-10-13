from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobPosting(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "serpapi"
    provider_id: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    posted_date: datetime | None = None
    source_url: str | None = None
    collected_at: datetime


class JobSearchResult(BaseModel):
    jobs: list[JobPosting]
    pages_fetched: int
    collected_at: datetime
    source: str = "SerpApi Google Jobs"
