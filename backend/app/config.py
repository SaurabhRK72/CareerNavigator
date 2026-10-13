from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareerNavigator AI API"
    environment: str = "development"
    serpapi_api_key: str | None = None
    serpapi_country_code: str = Field(default="in", min_length=2, max_length=2)
    serpapi_language: str = Field(default="en", min_length=2, max_length=5)
    serpapi_max_pages: int = Field(default=3, ge=1, le=10)
    job_api_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CAREERCOMPASS_",
        extra="ignore",
    )


settings = Settings()
