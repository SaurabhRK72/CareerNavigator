from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.collectors.adzuna import JobPosting
from backend.app.main import app
from backend.app.services.jobs import clean_jobs, extract_skills

client = TestClient(app)
COLLECTED_AT = datetime(2026, 10, 12, tzinfo=timezone.utc)


def make_job(**overrides: object) -> JobPosting:
    values: dict[str, object] = {
        "provider": "adzuna",
        "provider_id": "job-1",
        "title": "  Data   Analyst ",
        "company": "Example Ltd",
        "location": "Mumbai, India",
        "description": "Use Python, SQL, pandas and Power BI.",
        "salary_min": 500000,
        "salary_max": 700000,
        "posted_date": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "source_url": "https://example.test/jobs/job-1",
        "collected_at": COLLECTED_AT,
    }
    values.update(overrides)
    return JobPosting.model_validate(values)


def test_skill_extraction_normalizes_aliases_and_avoids_substrings() -> None:
    skills = extract_skills(
        "Python3, SQL, PowerBI, and machine-learning. "
        "The role expects a pythonista."
    )

    assert skills == ["Python", "SQL", "Power BI", "Machine Learning"]


def test_clean_jobs_normalizes_fields_and_reports_missing_data() -> None:
    source = make_job(
        title="  DATA \n analyst ",
        location=" Mumbai   India ",
        description="Use Python, SQL, pandas and Power BI.",
        company="Example Ltd",
        source_url="n/a",
    )

    result = clean_jobs([source])
    job = result.jobs[0]

    assert job.title == "DATA analyst"
    assert job.normalized_title == "data analyst"
    assert job.location == "Mumbai India"
    assert job.normalized_location == "mumbai india"
    assert job.description == "Use Python, SQL, pandas and Power BI."
    assert job.skills == ["Python", "SQL", "Power BI", "Pandas"]
    assert job.collected_at == source.collected_at
    assert result.quality_report.input_count == 1
    assert result.quality_report.unique_count == 1
    assert result.quality_report.missing_field_counts["source_url"] == 1


def test_deduplicates_by_provider_identifier_and_keeps_most_complete_record() -> None:
    sparse = make_job(
        title="Data Analyst",
        company=None,
        description=None,
        source_url=None,
    )
    complete = make_job(
        title="Data Analyst",
        company="Example Ltd",
        description="Python and SQL",
        source_url="https://example.test/jobs/job-1",
    )

    result = clean_jobs([sparse, complete])

    assert result.quality_report.duplicate_count == 1
    assert result.quality_report.unique_count == 1
    assert result.jobs[0].company == "Example Ltd"


def test_fallback_deduplication_uses_normalized_job_identity() -> None:
    first = make_job(
        provider_id=None,
        title="Data   Analyst",
        posted_date=None,
    )
    second = make_job(
        provider_id=None,
        title=" data analyst ",
        company="Example Ltd",
        location="Mumbai, India",
        posted_date=None,
    )

    result = clean_jobs([first, second])

    assert result.quality_report.duplicate_count == 1
    assert result.quality_report.unique_count == 1


def test_records_without_identity_fields_are_not_aggressively_merged() -> None:
    first = make_job(provider_id=None, company=None, location=None)
    second = make_job(provider_id=None, company=None, location=None)

    result = clean_jobs([first, second])

    assert result.quality_report.duplicate_count == 0
    assert result.quality_report.unique_count == 2


def test_missing_title_is_excluded_and_invalid_salary_is_cleared() -> None:
    missing_title = make_job(title="unknown")
    invalid_salary = make_job(salary_min=900000, salary_max=500000)

    result = clean_jobs([missing_title, invalid_salary])

    assert result.quality_report.excluded_missing_title_count == 1
    assert result.quality_report.invalid_salary_count == 1
    assert result.jobs[0].salary_min is None
    assert result.jobs[0].salary_max is None


def test_clean_endpoint_returns_jobs_and_quality_report() -> None:
    job = make_job()
    response = client.post(
        "/api/jobs/clean",
        json={"jobs": [job.model_dump(mode="json")]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"][0]["normalized_title"] == "data analyst"
    assert payload["jobs"][0]["skills"] == [
        "Python",
        "SQL",
        "Power BI",
        "Pandas",
    ]
    assert payload["quality_report"]["input_count"] == 1
    assert payload["quality_report"]["unique_count"] == 1


def test_clean_endpoint_rejects_empty_batch() -> None:
    response = client.post("/api/jobs/clean", json={"jobs": []})

    assert response.status_code == 422
