import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.collectors.job_posting import JobPosting
from backend.app.schemas.jobs import CleanedJobPosting, DataQualityReport

SKILL_DICTIONARY_PATH = Path(__file__).parent.parent / "data" / "skills.json"
_MISSING_TEXT = {"", "-", "n/a", "na", "none", "null", "unknown"}
_MISSING_FIELDS = (
    "title",
    "company",
    "location",
    "description",
    "posted_date",
    "salary_min",
    "salary_max",
    "source_url",
)


class JobCleaningResult(BaseModel):
    jobs: list[CleanedJobPosting]
    quality_report: DataQualityReport


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    category: str = Field(pattern="^(technical|soft)$")
    aliases: list[str] = Field(default_factory=list)


def load_skill_dictionary(
    dictionary_path: Path = SKILL_DICTIONARY_PATH,
) -> list[SkillDefinition]:
    """Load canonical skills and aliases from the editable JSON dictionary."""
    try:
        payload = json.loads(dictionary_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(
            f"Could not read the skill dictionary at {dictionary_path}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"The skill dictionary at {dictionary_path} is not valid JSON."
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("skills"), list):
        raise RuntimeError(
            f"The skill dictionary at {dictionary_path} must contain a skills list."
        )

    skills = [SkillDefinition.model_validate(item) for item in payload["skills"]]
    names = [skill.name.casefold() for skill in skills]
    if len(names) != len(set(names)):
        raise RuntimeError("The skill dictionary contains duplicate skill names.")
    return skills


def normalize_text(value: str | None) -> str | None:
    """Trim, collapse whitespace, and standardize common missing-value markers."""
    if value is None:
        return None
    normalized = " ".join(value.split())
    if normalized.casefold() in _MISSING_TEXT:
        return None
    return normalized


def extract_skills(
    text: str,
    skill_dictionary: Iterable[SkillDefinition] | None = None,
) -> list[str]:
    """Extract canonical skills using case-insensitive, whole-token matches."""
    definitions = (
        list(skill_dictionary)
        if skill_dictionary is not None
        else load_skill_dictionary()
    )
    found: list[str] = []
    searchable_text = text.casefold()

    for skill in definitions:
        terms = [skill.name, *skill.aliases]
        if any(_contains_term(searchable_text, term) for term in terms):
            found.append(skill.name)

    return found


def clean_jobs(
    raw_jobs: Iterable[JobPosting],
    skill_dictionary: Iterable[SkillDefinition] | None = None,
) -> JobCleaningResult:
    """Normalize, deduplicate, and enrich source jobs without mutating them."""
    input_jobs = list(raw_jobs)
    definitions = (
        list(skill_dictionary)
        if skill_dictionary is not None
        else load_skill_dictionary()
    )
    missing_field_counts = {
        field: sum(_is_missing(getattr(job, field)) for job in input_jobs)
        for field in _MISSING_FIELDS
    }

    accepted: list[CleanedJobPosting] = []
    excluded_missing_title_count = 0
    invalid_salary_count = 0
    for raw_job in input_jobs:
        title = normalize_text(raw_job.title)
        if title is None:
            excluded_missing_title_count += 1
            continue

        company = normalize_text(raw_job.company)
        location = normalize_text(raw_job.location)
        description = normalize_text(raw_job.description)
        source_url = normalize_text(raw_job.source_url)

        salary_min = raw_job.salary_min
        salary_max = raw_job.salary_max
        if (
            (salary_min is not None and salary_min < 0)
            or (salary_max is not None and salary_max < 0)
            or (
                salary_min is not None
                and salary_max is not None
                and salary_min > salary_max
            )
        ):
            salary_min = None
            salary_max = None
            invalid_salary_count += 1

        searchable_text = " ".join(part for part in (title, description) if part)
        accepted.append(
            CleanedJobPosting(
                **raw_job.model_dump(
                    exclude={
                        "title",
                        "company",
                        "location",
                        "description",
                        "source_url",
                        "salary_min",
                        "salary_max",
                    }
                ),
                title=title,
                company=company,
                location=location,
                normalized_title=title.casefold(),
                normalized_location=location.casefold() if location else None,
                description=description,
                source_url=source_url,
                salary_min=salary_min,
                salary_max=salary_max,
                skills=extract_skills(searchable_text, definitions),
            )
        )

    unique_by_key: dict[tuple[str, ...], tuple[int, CleanedJobPosting]] = {}
    duplicate_count = 0
    for index, job in enumerate(accepted):
        key = _deduplication_key(job, index)
        existing = unique_by_key.get(key)
        if existing is None:
            unique_by_key[key] = (index, job)
            continue

        duplicate_count += 1
        existing_index, existing_job = existing
        if _completeness_score(job) > _completeness_score(existing_job):
            unique_by_key[key] = (existing_index, job)

    unique_jobs = [
        job
        for _, job in sorted(unique_by_key.values(), key=lambda item: item[0])
    ]
    report = DataQualityReport(
        input_count=len(input_jobs),
        accepted_count=len(accepted),
        excluded_missing_title_count=excluded_missing_title_count,
        duplicate_count=duplicate_count,
        unique_count=len(unique_jobs),
        invalid_salary_count=invalid_salary_count,
        missing_field_counts=missing_field_counts,
    )
    return JobCleaningResult(jobs=unique_jobs, quality_report=report)


def _contains_term(text: str, term: str) -> bool:
    words = term.casefold().strip().split()
    if not words:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(word) for word in words)
    pattern += r"(?![a-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return normalize_text(value) is None
    return False


def _deduplication_key(
    job: CleanedJobPosting,
    input_index: int,
) -> tuple[str, ...]:
    provider_id = normalize_text(job.provider_id)
    provider = normalize_text(job.provider) or "unknown"
    if provider_id:
        return ("provider_id", provider.casefold(), provider_id.casefold())

    company = normalize_text(job.company)
    location = normalize_text(job.location)
    if not company or not location:
        return ("unique_record", str(input_index))

    posted_date = job.posted_date
    date_key = posted_date.isoformat() if posted_date else ""
    return (
        "fallback",
        job.normalized_title,
        company.casefold(),
        location.casefold(),
        date_key,
    )


def _completeness_score(job: CleanedJobPosting) -> int:
    return sum(
        getattr(job, field) is not None
        for field in (
            "company",
            "location",
            "description",
            "salary_min",
            "salary_max",
            "posted_date",
            "source_url",
        )
    )
