import pytest

from app.config import Settings, PlanLimits, load_plan_limits


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


class TestLoadPlanLimits:
    def test_load_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "plans.yaml"
        yaml_file.write_text(
            "free:\n"
            "  rate_limit: 5\n"
            "  monthly_quota: 50\n"
            "  max_file_size_mb: 25\n"
            "paid:\n"
            "  rate_limit: 60\n"
            "  monthly_quota: 5000\n"
            "  max_file_size_mb: 100\n"
        )
        plans = load_plan_limits(yaml_file)
        assert set(plans.keys()) == {"free", "paid"}
        assert plans["free"].rate_limit == 5
        assert plans["free"].monthly_quota == 50
        assert plans["free"].max_file_size_mb == 25
        assert plans["paid"].rate_limit == 60
        assert plans["paid"].monthly_quota == 5000
        assert plans["paid"].max_file_size_mb == 100

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_plan_limits(tmp_path / "nonexistent.yaml")

    def test_invalid_schema_raises(self, tmp_path):
        yaml_file = tmp_path / "plans.yaml"
        yaml_file.write_text("free:\n  rate_limit: 5\n")
        with pytest.raises(Exception):
            load_plan_limits(yaml_file)

    def test_empty_file_raises(self, tmp_path):
        yaml_file = tmp_path / "plans.yaml"
        yaml_file.write_text("")
        with pytest.raises(ValueError):
            load_plan_limits(yaml_file)


class TestSettingsGetPlanLimits:
    def test_get_valid_plan(self, tmp_path):
        yaml_file = tmp_path / "plans.yaml"
        yaml_file.write_text(
            "free:\n"
            "  rate_limit: 5\n"
            "  monthly_quota: 50\n"
            "  max_file_size_mb: 25\n"
        )
        settings = Settings(_env_file=None, plans_file=str(yaml_file))
        limits = settings.get_plan_limits("free")
        assert isinstance(limits, PlanLimits)
        assert limits.rate_limit == 5

    def test_unknown_plan_raises(self, tmp_path):
        yaml_file = tmp_path / "plans.yaml"
        yaml_file.write_text(
            "free:\n"
            "  rate_limit: 5\n"
            "  monthly_quota: 50\n"
            "  max_file_size_mb: 25\n"
        )
        settings = Settings(_env_file=None, plans_file=str(yaml_file))
        with pytest.raises(KeyError, match="Unknown plan"):
            settings.get_plan_limits("enterprise")

    def test_env_var_override_plans_file(self, monkeypatch, tmp_path):
        yaml_file = tmp_path / "custom.yaml"
        yaml_file.write_text(
            "pro:\n"
            "  rate_limit: 120\n"
            "  monthly_quota: 20000\n"
            "  max_file_size_mb: 500\n"
        )
        monkeypatch.setenv("SLICEOPS_PLANS_FILE", str(yaml_file))
        settings = Settings()
        limits = settings.get_plan_limits("pro")
        assert limits.rate_limit == 120
