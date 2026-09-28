from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "CloudFlow"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://cloudflow:cloudflow@localhost:5432/cloudflow"
    jwt_secret: str = "development-only-change-me"
    jwt_expire_minutes: int = 60
    aws_region: str = "ap-south-1"
    aws_profile: str | None = None
    aws_s3_bucket: str = ""
    aws_sqs_queue_url: str = ""
    aws_sqs_visibility_timeout: int = 180
    aws_endpoint_url: str | None = None
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    presigned_url_seconds: int = 300
    log_level: str = "INFO"

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


