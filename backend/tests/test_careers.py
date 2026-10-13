from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.session import get_db, get_optional_db
from backend.app.main import app
from backend.app.models import (
    CareerRole,
    LearningResource,
    LearningRoadmap,
    RoadmapMilestone,
)
from backend.app.schemas.careers import (
    LearningRoadmapRequest,
    StudentProfileInput,
    StudentSkillInput,
)
from backend.app.db.init_db import seed_reference_data
from backend.app.services.careers import (
    analyze_skill_gaps,
    create_learning_roadmap,
    get_career_roles,
    recommend_careers,
)

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
        app.dependency_overrides[get_optional_db] = lambda: session
        try:
            yield session
        finally:
            app.dependency_overrides.clear()
            session.close()
    Base.metadata.drop_all(bind=engine)


def test_role_catalog_is_explicit_and_available_without_database() -> None:
    response = client.get("/api/careers/roles")

    assert response.status_code == 200
    roles = response.json()
    assert {role["id"] for role in roles} >= {
        "data-analyst",
        "business-intelligence-analyst",
        "data-scientist",
        "data-engineer",
    }
    assert all(role["required_skill_count"] > 0 for role in roles)


def test_recommendations_return_explanations_and_weighted_scores() -> None:
    response = client.post(
        "/api/careers/recommendations",
        json={
            "technical_skills": [
                {"name": "SQL", "level": "intermediate"},
                {"name": "Excel", "level": "intermediate"},
                {"name": "python3", "level": "beginner"},
                {"name": "My made-up skill", "level": "advanced"},
            ],
            "education": "IT Engineering",
            "experience_years": 0,
            "interests": ["analytics"],
            "preferred_location": "Pune",
            "preferred_roles": ["Data Analyst"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendations"]
    assert payload["recommendations"][0]["role_id"] == "data-analyst"
    assert payload["recommendations"][0]["match_score"] > 0
    assert payload["recommendations"][0]["matching_skills"]
    assert payload["recommendations"][0]["missing_skills"]
    assert "weighted skill coverage" in payload["scoring_method"].lower()
    assert "not a probability" in payload["score_disclaimer"].lower()
    assert payload["unknown_profile_skills"] == ["My made-up skill"]
    assert "do not change the score" in payload["recommendations"][0][
        "preference_note"
    ]


def test_preferred_role_limits_recommendations_to_matching_catalog_roles() -> None:
    result = recommend_careers(
        StudentProfileInput(
            technical_skills=[StudentSkillInput(name="SQL")],
            preferred_roles=["Data Engineer"],
        )
    )

    assert [role.role_id for role in result.recommendations] == ["data-engineer"]


def test_skill_gaps_distinguish_possessed_partial_and_missing() -> None:
    app.dependency_overrides[get_optional_db] = lambda: None
    try:
        response = client.post(
            "/api/careers/skill-gaps?role_id=data-analyst",
            json={
                "technical_skills": [
                    {"name": "SQL", "level": "advanced"},
                    {"name": "Excel", "level": "beginner"},
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert "SQL" in {item["skill"] for item in payload["possessed"]}
    assert "Excel" in {item["skill"] for item in payload["partial"]}
    assert "Python" in {item["skill"] for item in payload["missing"]}
    assert payload["market_demand_available"] is False
    assert payload["priority_gaps"]


def test_unknown_role_returns_not_found() -> None:
    response = client.post(
        "/api/careers/skill-gaps?role_id=unknown-role",
        json={"technical_skills": []},
    )

    assert response.status_code == 404


def test_gap_priority_uses_market_demand_when_jobs_exist(database: Session) -> None:
    from datetime import datetime, timezone

    payload = {
        "provider": "adzuna",
        "provider_id": "career-market-1",
        "title": "Data Analyst",
        "company": "Example",
        "location": "Pune",
        "description": "Python and SQL",
        "posted_date": "2026-10-01T00:00:00Z",
        "source_url": "https://example.test/career-market-1",
        "collected_at": datetime(2026, 10, 12, tzinfo=timezone.utc).isoformat(),
    }
    saved = client.post("/api/jobs/process", json={"jobs": [payload]})
    assert saved.status_code == 200, saved.text

    result = analyze_skill_gaps(
        StudentProfileInput(technical_skills=[StudentSkillInput(name="SQL")]),
        "data-analyst",
        database,
    )

    assert result.market_demand_available is True
    python_gap = next(item for item in result.missing if item.skill == "Python")
    assert python_gap.market_demand_percentage == 100
    assert "market demand" in python_gap.explanation.lower()


def test_roadmap_uses_verified_resources_and_beginner_tasks() -> None:
    request = LearningRoadmapRequest(
        role_id="data-analyst",
        weekly_study_hours=4,
        profile=StudentProfileInput(
            technical_skills=[StudentSkillInput(name="SQL", level="intermediate")]
        ),
    )
    result = create_learning_roadmap(request)

    assert result.total_weeks > 0
    assert result.weekly_study_hours == 4
    assert result.milestones
    assert all(item.goal and item.practice_task and item.mini_project for item in result.milestones)
    python_milestone = next(item for item in result.milestones if item.skill == "Python")
    assert python_milestone.resource is not None
    assert python_milestone.resource.url == "https://docs.python.org/3/tutorial/"
    assert python_milestone.resource.last_verified == "2026-10-13"


def test_roadmap_does_not_invent_resource_links_for_uncatalogued_skills() -> None:
    request = LearningRoadmapRequest(
        role_id="data-analyst",
        profile=StudentProfileInput(technical_skills=[]),
    )
    result = create_learning_roadmap(request)

    excel_milestone = next(item for item in result.milestones if item.skill == "Excel")
    assert excel_milestone.resource is None


def test_roadmap_endpoint_validates_study_hours() -> None:
    response = client.post(
        "/api/careers/roadmaps",
        json={
            "role_id": "data-analyst",
            "weekly_study_hours": 100,
            "profile": {"technical_skills": []},
        },
    )

    assert response.status_code == 422


def test_database_initializer_seeds_reference_data_and_roadmap_is_persisted(
    database: Session,
) -> None:
    with database.begin():
        seed_reference_data(database)
    with database.begin():
        seed_reference_data(database)

    assert database.query(CareerRole).count() == 4
    assert database.query(LearningResource).count() == 9
    resource = database.query(LearningResource).first()
    assert resource is not None
    assert resource.last_verified_at is not None

    response = client.post(
        "/api/careers/roadmaps",
        json={
            "role_id": "data-analyst",
            "weekly_study_hours": 4,
            "profile": {
                "technical_skills": [
                    {"name": "SQL", "level": "intermediate"},
                ]
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["roadmap_id"] is not None
    assert database.scalar(select(CareerRole).where(CareerRole.slug == "data-analyst"))
    record = database.get(LearningRoadmap, payload["roadmap_id"])
    assert record is not None
    assert record.weekly_study_hours == 4
    assert len(record.milestones) == payload["total_weeks"]
    assert database.query(RoadmapMilestone).count() == payload["total_weeks"]
