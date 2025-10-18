"""Configuration helpers for the mock ADB server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore


class ConfigurationError(RuntimeError):
    """Raised when a configuration file cannot be processed."""


def load_config(path: str | Path) -> Dict[str, Any]:
    """Load a configuration file in JSON or YAML format.

    Parameters
    ----------
    path:
        File system path to the configuration file.

    Returns
    -------
    dict
        Parsed configuration data.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise ConfigurationError(f"Configuration file '{file_path}' does not exist.")

    suffix = file_path.suffix.lower()
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            if suffix == ".json":
                return json.load(fh)
            if suffix in {".yaml", ".yml"}:
                if yaml is None:
                    raise ConfigurationError(
                        "YAML configuration requested but PyYAML is not installed."
                    )
                return yaml.safe_load(fh)
            raise ConfigurationError(
                f"Unsupported configuration format '{suffix}'. Use JSON or YAML."
            )
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ConfigurationError(f"Invalid JSON configuration: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigurationError(f"Failed to parse configuration: {exc}") from exc
