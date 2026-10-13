from pydantic import BaseModel, Field

from backend.app.collectors.job_posting import JobPosting
from backend.app.schemas.jobs import DataQualityReport


class ProcessJobsRequest(BaseModel):
    jobs: list[JobPosting] = Field(min_length=1, max_length=500)


class ProcessJobsResponse(BaseModel):
    raw_saved_count: int
    jobs_created_count: int
    jobs_updated_count: int
    quality_report: DataQualityReport
