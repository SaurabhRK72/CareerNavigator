import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.collectors.adzuna import (
    AdzunaAPIError,
    AdzunaJobCollector,
    AdzunaRateLimitError,
    AdzunaTransportError,
)
from backend.app.collectors.job_posting import JobPosting, JobSearchResult
from backend.app import main as main_module
from backend.app.main import app

client = TestClient(app)


def test_health_check_returns_application_status() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "CareerNavigator AI API",
    }


def test_openapi_document_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "CareerNavigator AI API"


def test_search_jobs_requires_provider_credentials(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "serpapi_api_key", None)

    response = client.get("/api/jobs/search", params={"query": "data analyst"})

    assert response.status_code == 503
    assert "SerpApi API key is not configured" in response.json()["detail"]


def test_search_jobs_uses_configured_india_serpapi(monkeypatch) -> None:
    class FakeCollector:
        def __init__(self, **kwargs) -> None:
            assert kwargs["api_key"] == "test-key"
            assert kwargs["country_code"] == "in"
            assert kwargs["language"] == "en"

        def search(self, query: str, location: str | None = None):
            assert query == "data analyst"
            assert location == "Pune"
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            return JobSearchResult(
                jobs=[
                    JobPosting(
                        provider="serpapi",
                        provider_id="job-1",
                        title="Data Analyst",
                        collected_at=now,
                    )
                ],
                pages_fetched=1,
                collected_at=now,
            )

    monkeypatch.setattr(main_module.settings, "serpapi_api_key", "test-key")
    monkeypatch.setattr(main_module, "SerpApiJobCollector", FakeCollector)

    response = client.get(
        "/api/jobs/search",
        params={"query": " data analyst ", "location": " Pune "},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "SerpApi Google Jobs"
    assert response.json()["jobs"][0]["provider"] == "serpapi"


def test_search_jobs_rejects_blank_query() -> None:
    response = client.get("/api/jobs/search", params={"query": "   "})

    assert response.status_code == 422


def test_collector_maps_fields_and_keeps_dates_distinct() -> None:
    payload = {
        "results": [
            {
                "id": 123,
                "title": " Data Analyst ",
                "company": {"display_name": "Example Ltd"},
                "location": {"display_name": "Mumbai"},
                "description": "Python and SQL",
                "salary_min": "500000",
                "salary_max": 700000,
                "created": "2026-10-01T10:30:00Z",
                "redirect_url": "https://example.test/job/123",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/jobs/in/search/1")
        assert request.url.params["what"] == "data analyst"
        assert request.url.params["where"] == "Mumbai"
        return httpx.Response(200, json=payload)

    collector = AdzunaJobCollector(
        app_id="test-id",
        app_key="test-key",
        country_code="in",
        transport=httpx.MockTransport(handler),
    )
    result = collector.search("data analyst", "Mumbai")

    assert result.pages_fetched == 1
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.provider_id == "123"
    assert job.title == "Data Analyst"
    assert job.company == "Example Ltd"
    assert job.salary_min == 500000
    assert job.posted_date is not None
    assert job.collected_at != job.posted_date


def test_collector_stops_pagination_when_page_is_not_full() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, json={"results": [{"id": "1", "title": "Analyst"}]})

    collector = AdzunaJobCollector(
        app_id="test-id",
        app_key="test-key",
        results_per_page=2,
        max_pages=3,
        transport=httpx.MockTransport(handler),
    )

    result = collector.search("analyst")

    assert len(result.jobs) == 1
    assert result.pages_fetched == 1
    assert len(requested_paths) == 1


def test_collector_does_not_exceed_configured_page_limit() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"results": [{"id": str(len(requested_paths)), "title": "Analyst"}]},
        )

    collector = AdzunaJobCollector(
        app_id="test-id",
        app_key="test-key",
        results_per_page=1,
        max_pages=2,
        transport=httpx.MockTransport(handler),
    )

    result = collector.search("analyst")

    assert result.pages_fetched == 2
    assert len(requested_paths) == 2
    assert requested_paths[-1].endswith("/search/2")


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (429, AdzunaRateLimitError),
        (500, AdzunaAPIError),
    ],
)
def test_collector_surfaces_provider_errors_without_exposing_credentials(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider error")

    collector = AdzunaJobCollector(
        app_id="private-id",
        app_key="private-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(expected_error) as error:
        collector.search("analyst")

    assert "private-id" not in str(error.value)
    assert "private-key" not in str(error.value)


def test_collector_handles_missing_fields_and_bad_optional_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": None,
                        "title": None,
                        "company": {},
                        "salary_min": "not a salary",
                        "created": "not a date",
                    }
                ]
            },
        )

    collector = AdzunaJobCollector(
        app_id="test-id",
        app_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    job = collector.search("analyst").jobs[0]

    assert job.provider_id is None
    assert job.title is None
    assert job.company is None
    assert job.salary_min is None
    assert job.posted_date is None


def test_collector_surfaces_connection_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-key must not leak", request=request)

    collector = AdzunaJobCollector(
        app_id="private-id",
        app_key="private-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AdzunaTransportError) as error:
        collector.search("analyst")

    assert "private-key" not in str(error.value)
