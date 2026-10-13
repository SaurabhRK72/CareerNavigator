from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.db import session as db_session
from backend.app.main import app
from backend.app.models import Job

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


def job_payload(
    provider_id: str,
    title: str,
    location: str,
    description: str,
    posted_date: str,
) -> dict[str, object]:
    return {
        "provider": "adzuna",
        "provider_id": provider_id,
        "title": title,
        "company": f"{provider_id} Ltd",
        "location": location,
        "description": description,
        "salary_min": 50000,
        "salary_max": 70000,
        "posted_date": posted_date,
        "source_url": f"https://example.test/jobs/{provider_id}",
        "collected_at": "2026-10-12T10:00:00Z",
    }


def seed_market(database: Session) -> None:
    jobs = [
        job_payload(
            "market-1",
            "Data Analyst",
            "Mumbai, India",
            "Python SQL pandas",
            "2026-10-01T00:00:00Z",
        ),
        job_payload(
            "market-2",
            "Data Scientist",
            "Pune, India",
            "Python machine learning statistics",
            "2026-10-05T00:00:00Z",
        ),
        job_payload(
            "market-3",
            "Senior Data Analyst",
            "Mumbai, India",
            "SQL Excel",
            "2026-09-20T00:00:00Z",
        ),
    ]
    response = client.post("/api/jobs/process", json={"jobs": jobs})
    assert response.status_code == 200, response.text


def test_market_summary_reports_unique_jobs_dates_sources_and_limitations(
    database: Session,
) -> None:
    seed_market(database)

    response = client.get("/api/market/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["unique_job_count"] == 3
    assert payload["source_names"] == ["adzuna"]
    assert payload["posted_date_range"] == {
        "start": "2026-09-20",
        "end": "2026-10-05",
    }
    assert payload["last_successful_refresh"] is not None
    assert payload["top_locations"][0] == {
        "name": "Mumbai, India",
        "job_count": 2,
    }
    assert payload["salary_available"] is False
    assert payload["experience_available"] is False
    assert payload["historical_trends_available"] is False


def test_skill_demand_uses_unique_filtered_job_denominator(
    database: Session,
) -> None:
    seed_market(database)

    response = client.get("/api/market/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_size"] == 3
    demand = {item["skill"]: item for item in payload["skills"]}
    assert demand["Python"]["job_count"] == 2
    assert demand["Python"]["demand_percentage"] == 66.67
    assert demand["SQL"]["job_count"] == 2
    assert demand["SQL"]["demand_percentage"] == 66.67


def test_market_filters_apply_to_role_location_skill_and_dates(
    database: Session,
) -> None:
    seed_market(database)

    response = client.get(
        "/api/market/skills",
        params=[
            ("role", "analyst"),
            ("location", "mumbai"),
            ("skill", "SQL"),
            ("posted_from", "2026-09-01"),
            ("posted_to", "2026-10-01"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_size"] == 2
    assert payload["filters"]["skills"] == ["SQL"]
    demand = {item["skill"]: item for item in payload["skills"]}
    assert demand["SQL"]["demand_percentage"] == 100
    assert demand["Python"]["demand_percentage"] == 50


def test_market_jobs_returns_filtered_paged_records(
    database: Session,
) -> None:
    seed_market(database)

    response = client.get(
        "/api/market/jobs",
        params={"role": "data", "offset": 1, "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_size"] == 3
    assert payload["offset"] == 1
    assert payload["limit"] == 1
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["normalized_title"] == "data scientist"


def test_market_endpoints_reject_reversed_date_range(
    database: Session,
) -> None:
    response = client.get(
        "/api/market/summary",
        params={
            "posted_from": "2026-10-10",
            "posted_to": "2026-10-01",
        },
    )

    assert response.status_code == 422
    assert "posted_from must be on or before posted_to" in response.json()["detail"]


def test_market_summary_returns_empty_sample_when_database_has_no_jobs(
    database: Session,
) -> None:
    response = client.get("/api/market/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["unique_job_count"] == 0
    assert payload["posted_date_range"] == {"start": None, "end": None}


def test_market_endpoints_require_database_configuration(monkeypatch) -> None:
    monkeypatch.setattr(db_session, "SessionLocal", None)
    response = client.get("/api/market/summary")

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
