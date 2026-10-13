from datetime import date, datetime, time, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import Job, JobSkill, RawJobPosting, Skill
from backend.app.schemas.jobs import CleanedJobPosting
from backend.app.schemas.market import (
    DateRange,
    MarketFilters,
    MarketGroupCount,
    MarketJobsResponse,
    MarketSkillsResponse,
    MarketSummaryResponse,
    SkillDemand,
)


def normalize_filters(
    location: str | None,
    role: str | None,
    skills: list[str] | None,
    posted_from: date | None,
    posted_to: date | None,
) -> MarketFilters:
    normalized_skills = sorted(
        {skill.strip() for skill in (skills or []) if skill.strip()},
        key=str.casefold,
    )
    return MarketFilters(
        location=location.strip() if location and location.strip() else None,
        role=role.strip() if role and role.strip() else None,
        skills=normalized_skills,
        posted_from=posted_from,
        posted_to=posted_to,
    )


def get_market_summary(
    session: Session,
    filters: MarketFilters,
) -> MarketSummaryResponse:
    jobs = _load_filtered_jobs(session, filters)
    posted_dates = [
        _as_utc(job.posted_date).date()
        for job in jobs
        if job.posted_date is not None
    ]
    sources = session.scalars(
        select(RawJobPosting.provider).distinct().order_by(RawJobPosting.provider)
    ).all()
    last_refresh = session.scalar(select(func.max(RawJobPosting.collected_at)))

    location_counts = _group_counts(
        (job.location or "Unknown" for job in jobs),
        limit=10,
    )
    role_counts = _group_counts((job.title for job in jobs), limit=10)

    return MarketSummaryResponse(
        unique_job_count=len(jobs),
        filters=filters,
        source_names=list(sources),
        posted_date_range=DateRange(
            start=min(posted_dates) if posted_dates else None,
            end=max(posted_dates) if posted_dates else None,
        ),
        last_successful_refresh=last_refresh,
        top_locations=location_counts,
        top_roles=role_counts,
        salary_available=False,
        salary_unavailable_reason=(
            "Salary currency and comparability metadata are not stored yet."
        ),
        experience_available=False,
        experience_unavailable_reason=(
            "Reliable structured experience-level data is not available yet."
        ),
        historical_trends_available=False,
        historical_trends_unavailable_reason=(
            "A search batch timestamp is not a historical market snapshot. "
            "Historical trends require scheduled, comparable refresh snapshots."
        ),
    )


def get_skill_demand(
    session: Session,
    filters: MarketFilters,
    limit: int,
) -> MarketSkillsResponse:
    jobs = _load_filtered_jobs(session, filters)
    sample_size = len(jobs)
    counts: dict[str, tuple[str, int]] = {}
    for job in jobs:
        for skill in job.skills:
            category, count = counts.get(skill.name, (skill.category, 0))
            counts[skill.name] = (category, count + 1)

    ranked = sorted(
        counts.items(),
        key=lambda item: (-item[1][1], item[0].casefold()),
    )[:limit]
    posted_dates = [
        _as_utc(job.posted_date).date()
        for job in jobs
        if job.posted_date is not None
    ]
    sources = session.scalars(
        select(RawJobPosting.provider).distinct().order_by(RawJobPosting.provider)
    ).all()

    return MarketSkillsResponse(
        sample_size=sample_size,
        filters=filters,
        source_names=list(sources),
        posted_date_range=DateRange(
            start=min(posted_dates) if posted_dates else None,
            end=max(posted_dates) if posted_dates else None,
        ),
        skills=[
            SkillDemand(
                skill=name,
                category=category,
                job_count=count,
                demand_percentage=round(count * 100 / sample_size, 2)
                if sample_size
                else 0.0,
            )
            for name, (category, count) in ranked
        ],
    )


def get_market_jobs(
    session: Session,
    filters: MarketFilters,
    offset: int,
    limit: int,
) -> MarketJobsResponse:
    jobs = _load_filtered_jobs(session, filters)
    return MarketJobsResponse(
        sample_size=len(jobs),
        offset=offset,
        limit=limit,
        filters=filters,
        jobs=[
            CleanedJobPosting(
                **{
                    **{
                        field: getattr(job, field)
                        for field in (
                            "provider",
                            "provider_id",
                            "title",
                            "company",
                            "location",
                            "description",
                            "salary_min",
                            "salary_max",
                            "posted_date",
                            "source_url",
                            "collected_at",
                        )
                    },
                    "normalized_title": job.normalized_title,
                    "normalized_location": job.normalized_location,
                    "skills": [skill.name for skill in job.skills],
                }
            )
            for job in jobs[offset : offset + limit]
        ],
    )


def _load_filtered_jobs(
    session: Session,
    filters: MarketFilters,
) -> list[Job]:
    statement: Select[tuple[Job]] = select(Job).options(selectinload(Job.skills))
    if filters.location:
        statement = statement.where(
            Job.normalized_location.contains(filters.location.casefold())
        )
    if filters.role:
        statement = statement.where(
            Job.normalized_title.contains(filters.role.casefold())
        )
    if filters.posted_from:
        start = datetime.combine(
            filters.posted_from,
            time.min,
            tzinfo=timezone.utc,
        )
        statement = statement.where(Job.posted_date >= start)
    if filters.posted_to:
        end = datetime.combine(
            filters.posted_to,
            time.max,
            tzinfo=timezone.utc,
        )
        statement = statement.where(Job.posted_date <= end)
    for skill_name in filters.skills:
        matching_job_ids = (
            select(JobSkill.job_id)
            .join(Skill, Skill.id == JobSkill.skill_id)
            .where(func.lower(Skill.name) == skill_name.casefold())
        )
        statement = statement.where(Job.id.in_(matching_job_ids))

    return list(session.scalars(statement.order_by(Job.id)).all())


def _group_counts(values, limit: int) -> list[MarketGroupCount]:
    counts: dict[str, int] = {}
    display_names: dict[str, str] = {}
    for value in values:
        name = " ".join(value.split()) or "Unknown"
        key = name.casefold()
        counts[key] = counts.get(key, 0) + 1
        display_names.setdefault(key, name)

    ranked = sorted(
        counts.items(),
        key=lambda item: (-item[1], display_names[item[0]].casefold()),
    )[:limit]
    return [
        MarketGroupCount(name=display_names[key], job_count=count)
        for key, count in ranked
    ]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
