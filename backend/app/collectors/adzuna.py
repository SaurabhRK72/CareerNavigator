from datetime import datetime, timezone
from typing import Any

import httpx
from backend.app.collectors.job_posting import JobPosting, JobSearchResult


class AdzunaAPIError(Exception):
    """A sanitized error returned by the job provider."""


class AdzunaRateLimitError(AdzunaAPIError):
    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("The job provider rate limit was reached.")
        self.retry_after = retry_after


class AdzunaTransportError(Exception):
    """A sanitized error raised while contacting the job provider."""


class AdzunaJobCollector:
    """Fetch a bounded number of job-search pages from the Adzuna API."""

    _API_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

    def __init__(
        self,
        app_id: str,
        app_key: str,
        country_code: str = "in",
        results_per_page: int = 20,
        max_pages: int = 3,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.country_code = country_code.lower()
        self.results_per_page = results_per_page
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def search(self, query: str, location: str | None = None) -> JobSearchResult:
        collected_at = datetime.now(timezone.utc)
        jobs: list[JobPosting] = []

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers={"Accept": "application/json"},
            ) as client:
                pages_fetched = 0
                for page_number in range(1, self.max_pages + 1):
                    response = self._request_page(
                        client,
                        page_number,
                        query,
                        location,
                    )
                    page_jobs = self._parse_results(response, collected_at)
                    pages_fetched += 1
                    jobs.extend(page_jobs)

                    if len(page_jobs) < self.results_per_page:
                        break
        except AdzunaAPIError:
            raise
        except httpx.TimeoutException as exc:
            raise AdzunaTransportError(
                "The job provider request timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise AdzunaTransportError(
                "Could not connect to the job provider."
            ) from exc

        return JobSearchResult(
            jobs=jobs,
            pages_fetched=pages_fetched,
            collected_at=collected_at,
            source="Adzuna",
        )

    def _request_page(
        self,
        client: httpx.Client,
        page_number: int,
        query: str,
        location: str | None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": self.results_per_page,
            "what": query,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location

        url = self._API_URL.format(
            country=self.country_code,
            page=page_number,
        )
        try:
            response = client.get(url, params=params)
        except httpx.TimeoutException:
            raise
        except httpx.RequestError:
            raise

        if response.status_code == 429:
            raise AdzunaRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise AdzunaAPIError(
                f"The job provider returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AdzunaAPIError(
                "The job provider returned an invalid JSON response."
            ) from exc

        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), list
        ):
            raise AdzunaAPIError(
                "The job provider response did not contain a results list."
            )
        return payload

    @staticmethod
    def _parse_results(
        payload: dict[str, Any],
        collected_at: datetime,
    ) -> list[JobPosting]:
        return [
            JobPosting(
                provider="adzuna",
                provider_id=_as_text(item.get("id")),
                title=_as_text(item.get("title")),
                company=_nested_text(item.get("company"), "display_name"),
                location=_nested_text(item.get("location"), "display_name"),
                description=_as_text(item.get("description")),
                salary_min=_as_float(item.get("salary_min")),
                salary_max=_as_float(item.get("salary_max")),
                posted_date=_as_datetime(item.get("created")),
                source_url=_as_text(item.get("redirect_url")),
                collected_at=collected_at,
            )
            for item in payload["results"]
            if isinstance(item, dict)
        ]


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nested_text(value: Any, key: str) -> str | None:
    if isinstance(value, dict):
        return _as_text(value.get(key))
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
