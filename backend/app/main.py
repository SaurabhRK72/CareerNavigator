import logging
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.collectors.job_posting import JobSearchResult
from backend.app.collectors.serpapi import (
    SerpApiError,
    SerpApiJobCollector,
    SerpApiRateLimitError,
    SerpApiTransportError,
)
from backend.app.config import settings
from backend.app.db.session import get_db, get_optional_db
from backend.app.schemas.careers import (
    CareerRecommendationsResponse,
    CareerRoleSummary,
    LearningRoadmapRequest,
    LearningRoadmapResponse,
    SkillGapResponse,
    StudentProfileInput,
)
from backend.app.schemas.jobs import CleanJobsRequest, CleanJobsResponse
from backend.app.schemas.market import (
    MarketFilters,
    MarketJobsResponse,
    MarketSkillsResponse,
    MarketSummaryResponse,
)
from backend.app.schemas.storage import ProcessJobsRequest, ProcessJobsResponse
from backend.app.services.analytics import (
    get_market_jobs,
    get_market_summary,
    get_skill_demand,
    normalize_filters,
)
from backend.app.services.careers import (
    analyze_skill_gaps,
    create_learning_roadmap,
    get_career_roles,
    persist_learning_roadmap,
    recommend_careers,
)
from backend.app.services.jobs import clean_jobs
from backend.app.services.storage import store_cleaned_jobs

app = FastAPI(title=settings.app_name)
logger = logging.getLogger(__name__)


@app.get("/api/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report whether the API process is responding."""
    return {
        "status": "ok",
        "application": settings.app_name,
    }


@app.get("/api/jobs/search", response_model=JobSearchResult, tags=["jobs"])
def search_jobs(
    query: str = Query(min_length=1, max_length=100),
    location: str | None = Query(default=None, max_length=100),
) -> JobSearchResult:
    """Fetch a bounded India-focused Google Jobs search through SerpApi."""
    query = query.strip()
    if not query:
        raise HTTPException(
            status_code=422,
            detail="Search query must contain at least one non-space character.",
        )

    if location is not None:
        location = location.strip() or None

    if not settings.serpapi_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "SerpApi API key is not configured. Set "
                "CAREERCOMPASS_SERPAPI_API_KEY in the backend environment."
            ),
        )

    collector = SerpApiJobCollector(
        api_key=settings.serpapi_api_key,
        country_code=settings.serpapi_country_code,
        language=settings.serpapi_language,
        max_pages=settings.serpapi_max_pages,
        timeout_seconds=settings.job_api_timeout_seconds,
    )
    try:
        return collector.search(query=query, location=location)
    except SerpApiRateLimitError as exc:
        headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers=headers,
        ) from exc
    except (SerpApiError, SerpApiTransportError) as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@app.post("/api/jobs/clean", response_model=CleanJobsResponse, tags=["jobs"])
def clean_job_postings(request: CleanJobsRequest) -> CleanJobsResponse:
    """Normalize and analyze a batch of collected source postings."""
    result = clean_jobs(request.jobs)
    return CleanJobsResponse(
        jobs=result.jobs,
        quality_report=result.quality_report,
    )


@app.post(
    "/api/jobs/process",
    response_model=ProcessJobsResponse,
    tags=["jobs"],
)
def process_and_store_jobs(
    request: ProcessJobsRequest,
    session: Session = Depends(get_db),
) -> ProcessJobsResponse:
    """Save source snapshots and persist cleaned job and skill records."""
    try:
        result = store_cleaned_jobs(session, request.jobs)
    except SQLAlchemyError as exc:
        logger.exception("Failed to persist a job batch.")
        raise HTTPException(
            status_code=503,
            detail="Could not save jobs to the database. Check database availability.",
        ) from exc

    return ProcessJobsResponse(
        raw_saved_count=result.raw_saved_count,
        jobs_created_count=result.jobs_created_count,
        jobs_updated_count=result.jobs_updated_count,
        quality_report=result.quality_report,
    )


def _market_filters(
    location: str | None,
    role: str | None,
    skill: list[str] | None,
    posted_from: date | None,
    posted_to: date | None,
) -> MarketFilters:
    if posted_from and posted_to and posted_from > posted_to:
        raise HTTPException(
            status_code=422,
            detail="posted_from must be on or before posted_to.",
        )
    return normalize_filters(location, role, skill, posted_from, posted_to)


@app.get(
    "/api/market/summary",
    response_model=MarketSummaryResponse,
    tags=["market"],
)
def market_summary(
    location: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None, max_length=100),
    skill: list[str] | None = Query(default=None, max_length=100),
    posted_from: date | None = Query(default=None),
    posted_to: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> MarketSummaryResponse:
    """Return filtered job counts, location/title groups, and data coverage."""
    filters = _market_filters(location, role, skill, posted_from, posted_to)
    try:
        return get_market_summary(session, filters)
    except SQLAlchemyError as exc:
        logger.exception("Could not calculate the market summary.")
        raise HTTPException(
            status_code=503,
            detail="Could not read market data from the database.",
        ) from exc


@app.get(
    "/api/market/skills",
    response_model=MarketSkillsResponse,
    tags=["market"],
)
def market_skills(
    location: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None, max_length=100),
    skill: list[str] | None = Query(default=None, max_length=100),
    posted_from: date | None = Query(default=None),
    posted_to: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> MarketSkillsResponse:
    """Return skill demand as a percentage of unique filtered job records."""
    filters = _market_filters(location, role, skill, posted_from, posted_to)
    try:
        return get_skill_demand(session, filters, limit)
    except SQLAlchemyError as exc:
        logger.exception("Could not calculate skill demand.")
        raise HTTPException(
            status_code=503,
            detail="Could not read market data from the database.",
        ) from exc


@app.get(
    "/api/market/jobs",
    response_model=MarketJobsResponse,
    tags=["market"],
)
def market_jobs(
    location: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None, max_length=100),
    skill: list[str] | None = Query(default=None, max_length=100),
    posted_from: date | None = Query(default=None),
    posted_to: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db),
) -> MarketJobsResponse:
    """Return a page of cleaned postings matching dashboard filters."""
    filters = _market_filters(location, role, skill, posted_from, posted_to)
    try:
        return get_market_jobs(session, filters, offset, limit)
    except SQLAlchemyError as exc:
        logger.exception("Could not list market jobs.")
        raise HTTPException(
            status_code=503,
            detail="Could not read market data from the database.",
        ) from exc


@app.get(
    "/api/careers/roles",
    response_model=list[CareerRoleSummary],
    tags=["careers"],
)
def career_roles() -> list[CareerRoleSummary]:
    """List the transparent, editable career-role requirement profiles."""
    return get_career_roles()


@app.post(
    "/api/careers/recommendations",
    response_model=CareerRecommendationsResponse,
    tags=["careers"],
)
def career_recommendations(
    profile: StudentProfileInput,
    limit: int = Query(default=4, ge=1, le=10),
) -> CareerRecommendationsResponse:
    """Rank roles by transparent, weighted content-based skill coverage."""
    try:
        return recommend_careers(profile, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/careers/skill-gaps",
    response_model=SkillGapResponse,
    tags=["careers"],
)
def career_skill_gaps(
    role_id: str = Query(min_length=1, max_length=100),
    profile: StudentProfileInput = ...,
    session: Session | None = Depends(get_optional_db),
) -> SkillGapResponse:
    """Classify role skills and prioritize gaps using stored market demand."""
    try:
        return analyze_skill_gaps(profile, role_id, session)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Could not calculate market-prioritized skill gaps.")
        raise HTTPException(
            status_code=503,
            detail="Could not read market data from the database.",
        ) from exc


@app.post(
    "/api/careers/roadmaps",
    response_model=LearningRoadmapResponse,
    tags=["careers"],
)
def career_roadmap(
    request: LearningRoadmapRequest,
    session: Session | None = Depends(get_optional_db),
) -> LearningRoadmapResponse:
    """Generate a weekly learning roadmap from role-specific skill gaps."""
    try:
        roadmap = create_learning_roadmap(request, session)
        if session is not None:
            roadmap.roadmap_id = persist_learning_roadmap(session, roadmap)
        return roadmap
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Could not create a market-informed learning roadmap.")
        raise HTTPException(
            status_code=503,
            detail="Could not read market data from the database.",
        ) from exc
