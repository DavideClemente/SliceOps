from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SLICEOPS_", "env_file": ".env"}

    # Slicers
    prusa_slicer_path: str = "prusa-slicer"
    bambu_studio_path: str = "bambu-studio"
    slicer_timeout_seconds: int = 300

    # Storage
    temp_dir: str = "/tmp/sliceops"
    gcode_ttl_minutes: int = 15
    sync_threshold_mb: int = 10
    max_file_size_mb: int = 100

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Job store
    job_ttl_seconds: int = 3600

    # Rate limiting (requests per minute per IP)
    rate_limit: int = 10

    # Logging + CORS
    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"
