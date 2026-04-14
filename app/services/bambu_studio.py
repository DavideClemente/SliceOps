import asyncio
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

from app.services.slicer import BaseSlicer, SliceParams, SliceResult


OUTPUT_FILENAME = "output.gcode.3mf"


class BambuStudioService(BaseSlicer):
    def __init__(self, executable: str = "bambu-studio", timeout: int = 300) -> None:
        self._executable = executable
        self._timeout = timeout

    async def slice(self, stl_path: str, output_dir: str, params: SliceParams) -> SliceResult:
        output_path = str(Path(output_dir) / OUTPUT_FILENAME)
        settings_path = self._write_process_settings(output_dir, params)
        filament_path = self._write_filament_settings(output_dir, params)
        cmd = self._build_command(stl_path, output_path, settings_path, filament_path)

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

        # Read gcode from inside the 3MF archive to parse metadata
        gcode_content = self._read_gcode_from_3mf(output_path)
        result = self._parse_gcode_metadata(gcode_content)
        return result

    @staticmethod
    def _write_process_settings(output_dir: str, params: SliceParams) -> str:
        settings = {
            "layer_height": str(params.layer_height),
            "sparse_infill_density": f"{params.infill_percent}%",
            "enable_support": "1" if params.support_material else "0",
            "nozzle_diameter": [str(params.nozzle_size)],
        }
        if params.print_speed is not None:
            settings["inner_wall_speed"] = str(params.print_speed)
            settings["outer_wall_speed"] = str(params.print_speed)

        path = str(Path(output_dir) / "process.json")
        Path(path).write_text(json.dumps(settings))
        return path

    @staticmethod
    def _write_filament_settings(output_dir: str, params: SliceParams) -> str:
        settings = {
            "filament_type": [params.filament_type],
            "filament_density": [str(params.filament_density)],
        }
        path = str(Path(output_dir) / "filament.json")
        Path(path).write_text(json.dumps(settings))
        return path

    @staticmethod
    def _build_command(
        stl_path: str,
        output_path: str,
        settings_path: str,
        filament_path: str,
    ) -> list[str]:
        return [
            "bambu-studio",
            "--slice", "0",
            "--export-3mf", output_path,
            "--load-settings", settings_path,
            "--load-filaments", filament_path,
            stl_path,
        ]

    @staticmethod
    def _read_gcode_from_3mf(path: str) -> str:
        """Read G-code content from inside a .gcode.3mf archive."""
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".gcode"):
                    return zf.read(name).decode("utf-8")
        return ""

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

            # BambuStudio uses same format as PrusaSlicer for these
            grams_match = re.match(r";\s*total filament used \[g\]\s*=\s*([\d.]+)", line)
            if grams_match:
                filament_grams = float(grams_match.group(1))

            mm_match = re.match(r";\s*filament used \[mm\]\s*=\s*([\d.]+)", line)
            if mm_match:
                filament_mm = float(mm_match.group(1))

            if line == ";LAYER_CHANGE":
                layer_count += 1

        return SliceResult(
            estimated_time_seconds=time_seconds,
            filament_used_grams=filament_grams,
            filament_used_meters=round(filament_mm / 1000, 2),
            layer_count=layer_count,
            output_filename=OUTPUT_FILENAME,
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
