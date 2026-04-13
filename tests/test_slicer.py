from app.services.slicer import SliceParams, SliceResult, BaseSlicer


class TestSliceParams:
    def test_defaults(self):
        params = SliceParams()
        assert params.layer_height == 0.2
        assert params.infill_percent == 20
        assert params.print_speed is None
        assert params.support_material is False
        assert params.filament_type == "PLA"
        assert params.nozzle_size == 0.4

    def test_custom(self):
        params = SliceParams(layer_height=0.1, infill_percent=80, filament_type="PETG")
        assert params.layer_height == 0.1
        assert params.infill_percent == 80


class TestSliceResult:
    def test_creation(self):
        result = SliceResult(
            estimated_time_seconds=3720,
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
        )
        assert result.estimated_time_seconds == 3720
        assert result.filament_used_grams == 28.4

    def test_human_time_hours_and_minutes(self):
        result = SliceResult(
            estimated_time_seconds=3720,
            filament_used_grams=0,
            filament_used_meters=0,
            layer_count=0,
        )
        assert result.human_time == "1h 2m"

    def test_human_time_minutes_only(self):
        result = SliceResult(
            estimated_time_seconds=90,
            filament_used_grams=0,
            filament_used_meters=0,
            layer_count=0,
        )
        assert result.human_time == "1m 30s"

    def test_human_time_seconds_only(self):
        result = SliceResult(
            estimated_time_seconds=45,
            filament_used_grams=0,
            filament_used_meters=0,
            layer_count=0,
        )
        assert result.human_time == "45s"

    def test_cost_calculation(self):
        result = SliceResult(
            estimated_time_seconds=100,
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
        )
        # 28.4g at $20/kg = 28.4 * 20 / 1000 = 0.568 -> rounded to 0.57
        cost = result.compute_cost(filament_cost_per_kg=20.0)
        assert cost == 0.57


class TestBaseSlicerIsAbstract:
    def test_cannot_instantiate(self):
        import pytest
        with pytest.raises(TypeError):
            BaseSlicer()
