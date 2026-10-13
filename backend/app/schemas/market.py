from datetime import date, datetime

from pydantic import BaseModel

from backend.app.schemas.jobs import CleanedJobPosting


class DateRange(BaseModel):
    start: date | None
    end: date | None


class MarketFilters(BaseModel):
    location: str | None = None
    role: str | None = None
    skills: list[str]
    posted_from: date | None = None
    posted_to: date | None = None


class MarketGroupCount(BaseModel):
    name: str
    job_count: int


class SkillDemand(BaseModel):
    skill: str
    category: str
    job_count: int
    demand_percentage: float


class MarketSummaryResponse(BaseModel):
    unique_job_count: int
    filters: MarketFilters
    source_names: list[str]
    posted_date_range: DateRange
    last_successful_refresh: datetime | None
    top_locations: list[MarketGroupCount]
    top_roles: list[MarketGroupCount]
    salary_available: bool
    salary_unavailable_reason: str
    experience_available: bool
    experience_unavailable_reason: str
    historical_trends_available: bool
    historical_trends_unavailable_reason: str


class MarketSkillsResponse(BaseModel):
    sample_size: int
    filters: MarketFilters
    source_names: list[str]
    posted_date_range: DateRange
    skills: list[SkillDemand]


class MarketJobsResponse(BaseModel):
    sample_size: int
    offset: int
    limit: int
    filters: MarketFilters
    jobs: list[CleanedJobPosting]
