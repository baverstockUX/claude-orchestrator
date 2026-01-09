"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "postgresql+asyncpg://orch_user:changeme@localhost:5432/orchestrator"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # AWS Bedrock
    aws_profile: str = "advanced-bedrock"
    aws_region: str = "eu-west-1"
    bedrock_model_id: str = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Orchestrator
    max_agents: int = 5
    task_timeout: int = 300  # seconds
    lock_timeout: int = 300  # seconds

    # Logging
    log_level: str = "INFO"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )


# Global settings instance
settings = Settings()
