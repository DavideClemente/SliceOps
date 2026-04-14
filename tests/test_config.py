from app.config import Settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("SLICEOPS_PRUSA_SLICER_PATH", raising=False)
    settings = Settings(_env_file=None)
    assert settings.sync_threshold_mb == 10
    assert settings.temp_dir == "/tmp/sliceops"
    assert settings.gcode_ttl_minutes == 15
    assert settings.slicer_timeout_seconds == 300
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.prusa_slicer_path == "prusa-slicer"
    assert settings.rate_limit == 10
    assert settings.max_file_size_mb == 100


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SLICEOPS_SYNC_THRESHOLD_MB", "25")
    monkeypatch.setenv("SLICEOPS_TEMP_DIR", "/custom/tmp")
    monkeypatch.setenv("SLICEOPS_RATE_LIMIT", "30")
    monkeypatch.setenv("SLICEOPS_MAX_FILE_SIZE_MB", "50")
    settings = Settings()
    assert settings.sync_threshold_mb == 25
    assert settings.temp_dir == "/custom/tmp"
    assert settings.rate_limit == 30
    assert settings.max_file_size_mb == 50


def test_no_auth_or_db_fields():
    """Config should not have auth, db, or billing fields."""
    settings = Settings()
    assert not hasattr(settings, "database_url")
    assert not hasattr(settings, "github_client_id")
    assert not hasattr(settings, "jwt_secret")
    assert not hasattr(settings, "admin_api_key")
    assert not hasattr(settings, "plans_file")
    assert not hasattr(settings, "auth_enabled")
