import asyncio
import re
from pathlib import Path

from app.services.slicer import BaseSlicer, SliceParams, SliceResult


class OrcaSlicerService(BaseSlicer):
    def __init__(self, executable: str = "orca-slicer", timeout: int = 300) -> None:
        self._executable = executable
        self._timeout = timeout

    async def slice(self, stl_path: str, output_dir: str, params: SliceParams) -> SliceResult:
        gcode_path = str(Path(output_dir) / "output.gcode")
        cmd = self._build_command(stl_path, gcode_path, params)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"Slicer timed out after {self._timeout}s")

        if process.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"Slicer failed (exit {process.returncode}): {error_msg}")

        gcode_content = Path(gcode_path).read_text()
        return self._parse_gcode_metadata(gcode_content)

    def _build_command(self, stl_path: str, gcode_path: str, params: SliceParams) -> list[str]:
        cmd = [
            self._executable,
            "--slice", "0",
            "--outputdir", str(Path(gcode_path).parent),
        ]
        cmd.append(stl_path)
        return cmd

    @staticmethod
    def _parse_gcode_metadata(gcode_content: str) -> SliceResult:
        time_seconds = 0
        filament_grams = 0.0
        filament_mm = 0.0
        layer_count = 0

        for line in gcode_content.splitlines():
            line = line.strip()

            time_match = re.match(
                r";\s*estimated printing time \(normal mode\)\s*=\s*(.+)", line
            )
            if time_match:
                time_seconds = _parse_time_string(time_match.group(1).strip())

            grams_match = re.match(r";\s*filament used \[g\]\s*=\s*([\d.]+)", line)
            if grams_match:
                filament_grams = float(grams_match.group(1))

            mm_match = re.match(r";\s*filament used \[mm\]\s*=\s*([\d.]+)", line)
            if mm_match:
                filament_mm = float(mm_match.group(1))

            layer_match = re.match(r";\s*total layers count\s*=\s*(\d+)", line)
            if layer_match:
                layer_count = int(layer_match.group(1))

        return SliceResult(
            estimated_time_seconds=time_seconds,
            filament_used_grams=filament_grams,
            filament_used_meters=round(filament_mm / 1000, 2),
            layer_count=layer_count,
        )


def _parse_time_string(time_str: str) -> int:
    total = 0
    hours = re.search(r"(\d+)h", time_str)
    minutes = re.search(r"(\d+)m", time_str)
    seconds = re.search(r"(\d+)s", time_str)
    if hours:
        total += int(hours.group(1)) * 3600
    if minutes:
        total += int(minutes.group(1)) * 60
    if seconds:
        total += int(seconds.group(1))
    return total
