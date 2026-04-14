from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SLICEOPS_", "env_file": ".env"}

    sync_threshold_mb: int = 10
    max_file_size_mb: int = 100
    temp_dir: str = "/tmp/sliceops"
    gcode_ttl_minutes: int = 15
    slicer_timeout_seconds: int = 300
    redis_url: str = "redis://localhost:6379/0"
    prusa_slicer_path: str = "prusa-slicer"
