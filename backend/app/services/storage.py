from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.collectors.job_posting import JobPosting
from backend.app.models import Job, RawJobPosting, Skill
from backend.app.schemas.jobs import CleanedJobPosting, DataQualityReport
from backend.app.services.jobs import clean_jobs, load_skill_dictionary


class JobStorageResult:
    def __init__(
        self,
        raw_saved_count: int,
        jobs_created_count: int,
        jobs_updated_count: int,
        quality_report: DataQualityReport,
    ) -> None:
        self.raw_saved_count = raw_saved_count
        self.jobs_created_count = jobs_created_count
        self.jobs_updated_count = jobs_updated_count
        self.quality_report = quality_report


def store_cleaned_jobs(
    session: Session,
    raw_jobs: list[JobPosting],
) -> JobStorageResult:
    """Save source snapshots and upsert cleaned jobs and their skill links."""
    cleaned = clean_jobs(raw_jobs)
    definitions = load_skill_dictionary()

    with session.begin():
        for raw_job in raw_jobs:
            session.add(
                RawJobPosting(
                    provider=raw_job.provider,
                    provider_id=raw_job.provider_id,
                    collected_at=raw_job.collected_at,
                    payload=raw_job.model_dump(mode="json"),
                )
            )

        skills_by_name: dict[str, Skill] = {}
        for definition in definitions:
            skill = session.scalar(
                select(Skill).where(Skill.name == definition.name)
            )
            if skill is None:
                skill = Skill(
                    name=definition.name,
                    category=definition.category,
                    aliases=definition.aliases,
                )
                session.add(skill)
            else:
                skill.category = definition.category
                skill.aliases = definition.aliases
            skills_by_name[definition.name] = skill

        session.flush()
        created_count = 0
        updated_count = 0
        for cleaned_job in cleaned.jobs:
            job = _find_existing_job(session, cleaned_job)
            if job is None:
                job = Job(
                    provider=cleaned_job.provider,
                    provider_id=cleaned_job.provider_id,
                )
                session.add(job)
                created_count += 1
            else:
                updated_count += 1

            _copy_job_fields(job, cleaned_job)
            job.skills = [
                skills_by_name[skill_name]
                for skill_name in cleaned_job.skills
            ]

        session.flush()

    return JobStorageResult(
        raw_saved_count=len(raw_jobs),
        jobs_created_count=created_count,
        jobs_updated_count=updated_count,
        quality_report=cleaned.quality_report,
    )


def _find_existing_job(
    session: Session,
    job: CleanedJobPosting,
) -> Job | None:
    if job.provider_id:
        return session.scalar(
            select(Job).where(
                Job.provider == job.provider,
                Job.provider_id == job.provider_id,
            )
        )

    if not job.company or not job.location:
        return None

    return session.scalar(
        select(Job).where(
            Job.provider == job.provider,
            Job.provider_id.is_(None),
            Job.normalized_title == job.normalized_title,
            Job.company == job.company,
            Job.location == job.location,
            Job.posted_date == job.posted_date,
        )
    )


def _copy_job_fields(job: Job, source: CleanedJobPosting) -> None:
    job.provider = source.provider
    job.provider_id = source.provider_id
    job.title = source.title or ""
    job.normalized_title = source.normalized_title
    job.company = source.company
    job.location = source.location
    job.normalized_location = source.normalized_location
    job.description = source.description
    job.salary_min = source.salary_min
    job.salary_max = source.salary_max
    job.posted_date = source.posted_date
    job.source_url = source.source_url
    job.collected_at = source.collected_at
