from app.config import Settings


def test_default_settings(monkeypatch):
    # Clear env var so .env file doesn't interfere
    monkeypatch.delenv("SLICEOPS_PRUSA_SLICER_PATH", raising=False)
    settings = Settings(_env_file=None)
    assert settings.sync_threshold_mb == 10
    assert settings.temp_dir == "/tmp/sliceops"
    assert settings.gcode_ttl_minutes == 15
    assert settings.slicer_timeout_seconds == 300
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.prusa_slicer_path == "prusa-slicer"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SLICEOPS_SYNC_THRESHOLD_MB", "25")
    monkeypatch.setenv("SLICEOPS_TEMP_DIR", "/custom/tmp")
    settings = Settings()
    assert settings.sync_threshold_mb == 25
    assert settings.temp_dir == "/custom/tmp"
