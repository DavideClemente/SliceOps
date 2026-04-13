from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SliceParams:
    layer_height: float = 0.2
    infill_percent: int = 20
    print_speed: float | None = None
    support_material: bool = False
    filament_type: str = "PLA"
    nozzle_size: float = 0.4


@dataclass
class SliceResult:
    estimated_time_seconds: int
    filament_used_grams: float
    filament_used_meters: float
    layer_count: int

    @property
    def human_time(self) -> str:
        total = self.estimated_time_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def compute_cost(self, filament_cost_per_kg: float) -> float:
        return round(self.filament_used_grams * filament_cost_per_kg / 1000, 2)


class BaseSlicer(ABC):
    @abstractmethod
    async def slice(self, stl_path: str, output_dir: str, params: SliceParams) -> SliceResult:
        ...
