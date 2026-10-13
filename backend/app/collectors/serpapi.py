from datetime import datetime, timezone
from typing import Any

import httpx

from backend.app.collectors.job_posting import JobPosting, JobSearchResult


class SerpApiError(Exception):
    """A sanitized error returned by SerpApi."""


class SerpApiRateLimitError(SerpApiError):
    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("SerpApi rate limit reached.")
        self.retry_after = retry_after


class SerpApiTransportError(Exception):
    """A sanitized error raised while contacting SerpApi."""


class SerpApiJobCollector:
    """Fetch a bounded Google Jobs search from SerpApi."""

    _API_URL = "https://serpapi.com/search.json"

    def __init__(
        self,
        api_key: str,
        country_code: str = "in",
        language: str = "en",
        max_pages: int = 3,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.country_code = country_code.lower()
        self.language = language.lower()
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def search(self, query: str, location: str | None = None) -> JobSearchResult:
        collected_at = datetime.now(timezone.utc)
        jobs: list[JobPosting] = []
        next_page_token: str | None = None

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers={"Accept": "application/json"},
            ) as client:
                pages_fetched = 0
                for _ in range(self.max_pages):
                    payload = self._request_page(
                        client,
                        query=query,
                        location=location,
                        next_page_token=next_page_token,
                    )
                    jobs.extend(self._parse_results(payload, collected_at))
                    pages_fetched += 1
                    pagination = payload.get("serpapi_pagination", {})
                    token = pagination.get("next_page_token", "")
                    next_page_token = token if isinstance(token, str) and token else None
                    if next_page_token is None:
                        break
        except SerpApiError:
            raise
        except httpx.TimeoutException as exc:
            raise SerpApiTransportError("SerpApi request timed out.") from exc
        except httpx.RequestError as exc:
            raise SerpApiTransportError("Could not connect to SerpApi.") from exc

        return JobSearchResult(
            jobs=jobs,
            pages_fetched=pages_fetched,
            collected_at=collected_at,
        )

    def _request_page(
        self,
        client: httpx.Client,
        query: str,
        location: str | None,
        next_page_token: str | None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "engine": "google_jobs",
            "q": query,
            "gl": self.country_code,
            "hl": self.language,
            "api_key": self.api_key,
        }
        if location:
            params["location"] = location
        if next_page_token:
            params["next_page_token"] = next_page_token

        try:
            response = client.get(self._API_URL, params=params)
        except (httpx.TimeoutException, httpx.RequestError):
            raise

        if response.status_code == 429:
            raise SerpApiRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise SerpApiError(f"SerpApi returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise SerpApiError("SerpApi returned an invalid JSON response.") from exc

        if not isinstance(payload, dict):
            raise SerpApiError("SerpApi returned an unexpected response.")
        if payload.get("error"):
            raise SerpApiError("SerpApi reported that the search could not be completed.")
        if not isinstance(payload.get("jobs_results"), list):
            raise SerpApiError("SerpApi response did not contain a jobs_results list.")
        pagination = payload.get("serpapi_pagination", {})
        if not isinstance(pagination, dict):
            payload["serpapi_pagination"] = {}
        return payload

    @staticmethod
    def _parse_results(
        payload: dict[str, Any],
        collected_at: datetime,
    ) -> list[JobPosting]:
        results: list[JobPosting] = []
        for item in payload["jobs_results"]:
            if not isinstance(item, dict):
                continue
            extensions = item.get("detected_extensions")
            if not isinstance(extensions, dict):
                extensions = {}
            results.append(
                JobPosting(
                    provider="serpapi",
                    provider_id=_text(item.get("job_id")),
                    title=_text(item.get("title")),
                    company=_text(item.get("company_name")),
                    location=_location_text(item.get("location")),
                    description=_text(item.get("description")),
                    posted_date=_date(extensions.get("posted_at")),
                    source_url=_text(item.get("share_link"))
                    or _first_apply_link(item.get("apply_options")),
                    collected_at=collected_at,
                )
            )
        return results


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        result = str(value).strip()
        return result or None
    return None


def _location_text(value: Any) -> str | None:
    if isinstance(value, list):
        return ", ".join(text for item in value if (text := _text(item)))
    return _text(value)


def _first_apply_link(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            link = _text(item.get("link"))
            if link:
                return link
    return None


def _date(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # Google Jobs commonly returns relative dates; do not invent an exact date.
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
