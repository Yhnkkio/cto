from __future__ import annotations

# Namespace package shim to enable `python -m cto` from a fresh checkout without installation.
# It loads the real Typer app from src/cto/cli.py without requiring installation.
import importlib.util
import os
import sys
from types import ModuleType

ROOT = os.path.dirname(os.path.dirname(__file__))
CLI_PATH = os.path.join(ROOT, "src", "cto", "cli.py")

spec = importlib.util.spec_from_file_location("_cto_cli_shim", CLI_PATH)
if spec is None or spec.loader is None:  # pragma: no cover - defensive
    raise SystemExit("Unable to locate CLI module at src/cto/cli.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)  # type: ignore[assignment]

app = getattr(module, "app")

if __name__ == "__main__":
    app()
