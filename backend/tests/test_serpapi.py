from datetime import datetime

import httpx
import pytest

from backend.app.collectors.serpapi import (
    SerpApiError,
    SerpApiJobCollector,
    SerpApiRateLimitError,
    SerpApiTransportError,
)


def test_collector_maps_google_jobs_to_common_posting_shape() -> None:
    payload = {
        "jobs_results": [
            {
                "job_id": "google-job-1",
                "title": "Data Analyst",
                "company_name": "Example Ltd",
                "location": "Pune, Maharashtra, India",
                "description": "SQL and Python role",
                "share_link": "https://jobs.google.com/example",
                "detected_extensions": {"posted_at": "2026-10-12T09:00:00Z"},
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "serpapi.com"
        assert request.url.params["engine"] == "google_jobs"
        assert request.url.params["q"] == "data analyst"
        assert request.url.params["location"] == "Pune"
        assert request.url.params["gl"] == "in"
        assert request.url.params["api_key"] == "test-key"
        return httpx.Response(200, json=payload)

    collector = SerpApiJobCollector(
        api_key="test-key",
        country_code="in",
        transport=httpx.MockTransport(handler),
    )
    result = collector.search("data analyst", "Pune")

    assert result.source == "SerpApi Google Jobs"
    assert result.pages_fetched == 1
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.provider == "serpapi"
    assert job.provider_id == "google-job-1"
    assert job.company == "Example Ltd"
    assert job.location == "Pune, Maharashtra, India"
    assert job.source_url == "https://jobs.google.com/example"
    assert job.posted_date == datetime.fromisoformat("2026-10-12T09:00:00+00:00")
    assert job.collected_at != job.posted_date


def test_collector_paginates_only_when_token_present_and_within_cap() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "jobs_results": [{"job_id": "1", "title": "Analyst"}],
                    "serpapi_pagination": {"next_page_token": "page-token"},
                },
            )
        return httpx.Response(200, json={"jobs_results": []})

    result = SerpApiJobCollector(
        api_key="test-key",
        max_pages=3,
        transport=httpx.MockTransport(handler),
    ).search("analyst")

    assert result.pages_fetched == 2
    assert len(result.jobs) == 1
    assert len(requests) == 2
    assert requests[1].url.params["next_page_token"] == "page-token"


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(429, SerpApiRateLimitError), (500, SerpApiError)],
)
def test_collector_sanitizes_http_errors(
    status: int,
    error_type: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="test-key must not leak")

    collector = SerpApiJobCollector(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(error_type) as error:
        collector.search("analyst")

    assert "test-key" not in str(error.value)


def test_collector_rejects_invalid_and_provider_error_responses() -> None:
    for payload in ({"error": "invalid key"}, {"unexpected": True}):
        collector = SerpApiJobCollector(
            api_key="private-key",
            transport=httpx.MockTransport(
                lambda request, body=payload: httpx.Response(200, json=body)
            ),
        )
        with pytest.raises(SerpApiError) as error:
            collector.search("analyst")
        assert "private-key" not in str(error.value)


def test_collector_handles_relative_posting_dates_and_missing_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs_results": [
                    {
                        "job_id": "relative-date",
                        "title": "Analyst",
                        "detected_extensions": {"posted_at": "3 days ago"},
                    },
                    "malformed row",
                ]
            },
        )

    result = SerpApiJobCollector(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ).search("analyst")

    assert len(result.jobs) == 1
    assert result.jobs[0].posted_date is None
    assert result.jobs[0].company is None
    assert result.jobs[0].source_url is None


def test_collector_sanitizes_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-key must not leak", request=request)

    collector = SerpApiJobCollector(
        api_key="private-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SerpApiTransportError) as error:
        collector.search("analyst")

    assert "private-key" not in str(error.value)
