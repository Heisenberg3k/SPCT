from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    output_file: Path = Path(r"D:\Dev\SPCT_Example\a.txt")
    runtime_dir: Path = BASE_DIR / "runtime"
    cli_path: str = "auto"
    model: str = ""
    timeout_seconds: float = 180.0
    click_at_pointer: bool = True

    def resolved_cli(self) -> str:
        if self.cli_path != "auto":
            path = Path(self.cli_path)
            if not path.is_absolute() and (BASE_DIR / path).is_file():
                return str((BASE_DIR / path).resolve())
            return self.cli_path
        bundled = BASE_DIR / ".tools" / "node_modules" / ".bin" / "copilot.cmd"
        return str(bundled) if bundled.is_file() else "copilot"


def load_settings(path: Path = BASE_DIR / "config.json") -> Settings:
    values = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if not isinstance(values, dict):
        raise ValueError("config.json must contain a JSON object.")
    unknown = values.keys() - Settings.__dataclass_fields__.keys()
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    for key in ("output_file", "runtime_dir"):
        if key in values:
            if not isinstance(values[key], str) or not values[key].strip():
                raise ValueError(f"{key} must be a nonempty path.")
            value = Path(values[key])
            values[key] = value if value.is_absolute() else BASE_DIR / value
    for key in ("cli_path", "model"):
        if key in values and not isinstance(values[key], str):
            raise ValueError(f"{key} must be a string.")
    timeout = values.get("timeout_seconds", 180)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 10 <= timeout <= 1800:
        raise ValueError("timeout_seconds must be between 10 and 1800.")
    if not isinstance(values.get("click_at_pointer", True), bool):
        raise ValueError("click_at_pointer must be true or false.")
    return Settings(**values)
