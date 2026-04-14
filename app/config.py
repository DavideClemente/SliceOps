from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class PlanLimits(BaseModel):
    rate_limit: int
    monthly_quota: int
    max_file_size_mb: int


def load_plan_limits(path: str | Path) -> dict[str, PlanLimits]:
    path = Path(path)
    if not path.is_absolute():
        # Resolve relative to the project root (parent of app/)
        project_root = Path(__file__).resolve().parent.parent
        path = project_root / path
    if not path.exists():
        raise FileNotFoundError(f"Plans file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"Plans file must be a non-empty YAML mapping: {path}")
    plans: dict[str, PlanLimits] = {}
    for name, values in raw.items():
        plans[name] = PlanLimits(**values)
    return plans


class Settings(BaseSettings):
    model_config = {"env_prefix": "SLICEOPS_", "env_file": ".env"}

    sync_threshold_mb: int = 10
    temp_dir: str = "/tmp/sliceops"
    gcode_ttl_minutes: int = 15
    slicer_timeout_seconds: int = 300
    redis_url: str = "redis://localhost:6379/0"
    prusa_slicer_path: str = "prusa-slicer"
    bambu_studio_path: str = "bambu-studio"

    # Phase 1: Logging + CORS
    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"

    # Phase 2: Job Store
    job_ttl_seconds: int = 3600

    # Phase 3: Auth
    admin_api_key: str = ""
    auth_enabled: bool = True

    # Phase 4: Plan limits via YAML
    plans_file: str = "config/plans.yaml"

    # Database
    database_url: str = "postgresql+asyncpg://sliceops:sliceops@localhost:5432/sliceops"

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 30

    # Base URL (for OAuth callback)
    base_url: str = "http://localhost:8000"

    @cached_property
    def _plan_limits(self) -> dict[str, PlanLimits]:
        return load_plan_limits(self.plans_file)

    def get_plan_limits(self, plan: str) -> PlanLimits:
        limits = self._plan_limits
        if plan not in limits:
            raise KeyError(f"Unknown plan: '{plan}'. Available plans: {list(limits.keys())}")
        return limits[plan]
