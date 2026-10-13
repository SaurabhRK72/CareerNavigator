from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.db import session as db_session
from backend.app.main import app
from backend.app.models import Job, JobSkill, RawJobPosting, Skill

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)
client = TestClient(app)


@pytest.fixture()
def database() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    with TestSessionLocal() as session:
        app.dependency_overrides[get_db] = lambda: session
        try:
            yield session
        finally:
            app.dependency_overrides.clear()
            session.close()
    Base.metadata.drop_all(bind=engine)


def make_job_payload() -> dict[str, object]:
    return {
        "provider": "adzuna",
        "provider_id": "storage-demo-1",
        "title": "Data Analyst",
        "company": "Demo Co",
        "location": "Mumbai",
        "description": "Use Python, SQL and Power BI.",
        "salary_min": 500000,
        "salary_max": 700000,
        "posted_date": datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
        "source_url": "https://example.test/jobs/storage-demo-1",
        "collected_at": datetime(2026, 10, 12, tzinfo=timezone.utc).isoformat(),
    }


def test_process_endpoint_persists_raw_clean_jobs_and_skill_links(
    database: Session,
) -> None:
    response = client.post(
        "/api/jobs/process",
        json={"jobs": [make_job_payload()]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_saved_count"] == 1
    assert payload["jobs_created_count"] == 1
    assert payload["jobs_updated_count"] == 0
    assert payload["quality_report"]["unique_count"] == 1

    job = database.scalar(select(Job))
    assert job is not None
    assert job.normalized_title == "data analyst"
    assert {skill.name for skill in job.skills} == {
        "Python",
        "SQL",
        "Power BI",
    }
    assert database.scalar(select(func.count()).select_from(RawJobPosting)) == 1
    assert database.scalar(select(func.count()).select_from(Skill)) >= 3
    assert database.scalar(select(func.count()).select_from(JobSkill)) == 3


def test_processing_same_provider_job_updates_clean_record_but_keeps_raw_snapshot(
    database: Session,
) -> None:
    first = make_job_payload()
    second = {
        **first,
        "description": "Updated role: Python, SQL and Tableau.",
        "collected_at": datetime(2026, 10, 13, tzinfo=timezone.utc).isoformat(),
    }

    first_response = client.post("/api/jobs/process", json={"jobs": [first]})
    second_response = client.post("/api/jobs/process", json={"jobs": [second]})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["jobs_created_count"] == 0
    assert second_response.json()["jobs_updated_count"] == 1
    assert database.scalar(select(func.count()).select_from(Job)) == 1
    assert database.scalar(select(func.count()).select_from(RawJobPosting)) == 2

    job = database.scalar(select(Job))
    assert job is not None
    assert "Tableau" in {skill.name for skill in job.skills}
    assert "Power BI" not in {skill.name for skill in job.skills}


def test_process_endpoint_requires_database_configuration(monkeypatch) -> None:
    monkeypatch.setattr(db_session, "SessionLocal", None)
    response = client.post(
        "/api/jobs/process",
        json={"jobs": [make_job_payload()]},
    )

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_process_endpoint_rejects_empty_batch(database: Session) -> None:
    response = client.post("/api/jobs/process", json={"jobs": []})

    assert response.status_code == 422
