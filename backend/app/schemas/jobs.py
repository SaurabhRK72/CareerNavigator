from pydantic import BaseModel, ConfigDict, Field

from backend.app.collectors.job_posting import JobPosting


class CleanedJobPosting(JobPosting):
    model_config = ConfigDict(extra="ignore")

    normalized_title: str
    normalized_location: str | None = None
    skills: list[str] = Field(default_factory=list)


class CleanJobsRequest(BaseModel):
    jobs: list[JobPosting] = Field(min_length=1, max_length=500)


class DataQualityReport(BaseModel):
    input_count: int
    accepted_count: int
    excluded_missing_title_count: int
    duplicate_count: int
    unique_count: int
    invalid_salary_count: int
    missing_field_counts: dict[str, int]


class CleanJobsResponse(BaseModel):
    jobs: list[CleanedJobPosting]
    quality_report: DataQualityReport
