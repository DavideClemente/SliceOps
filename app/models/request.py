from pydantic import BaseModel, Field


class SliceRequest(BaseModel):
    layer_height: float = Field(default=0.2, gt=0, description="Layer height in mm")
    infill_percent: int = Field(default=20, ge=0, le=100, description="Infill percentage")
    print_speed: float | None = Field(default=None, gt=0, description="Print speed in mm/s")
    support_material: bool = Field(default=False, description="Enable support material")
    filament_type: str = Field(default="PLA", description="Filament type (PLA, PETG, ABS, TPU)")
    filament_cost: float = Field(default=20.0, ge=0, description="Filament cost per kg")
    nozzle_size: float = Field(default=0.4, gt=0, description="Nozzle diameter in mm")
