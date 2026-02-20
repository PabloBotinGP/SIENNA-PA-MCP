#!/usr/bin/env python3
"""Generate API index files from locally installed PowerAnalytics.jl.

Run this once after installing or updating PowerAnalytics.jl:
    python generate_index.py

Output:
    resources/api_index.md
    resources/component_types.md
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add parent directory to path so we can import server constants
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from mcp_servers.poweranalytics.server import API_INDEX_SCRIPT, COMPONENT_TYPES_SCRIPT

# Reuse same config as server.py
JULIA_EXECUTABLE = os.environ.get("JULIA_EXECUTABLE", "julia")
PA_PROJECT_PATH = os.environ.get("PA_PROJECT_PATH", ".")
PA_SYSIMAGE_PATH = os.environ.get("PA_SYSIMAGE_PATH", "")
RESOURCES_DIR = Path(__file__).parent / "resources"


def run_julia_sync(script: str) -> str:
    """Run a Julia script and return stdout."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jl", delete=False) as f:
        f.write(script)
        tmp_path = f.name
    try:
        cmd = [JULIA_EXECUTABLE]
        if PA_SYSIMAGE_PATH and Path(PA_SYSIMAGE_PATH).is_file():
            cmd.append(f"--sysimage={PA_SYSIMAGE_PATH}")
        cmd += [f"--project={PA_PROJECT_PATH}", tmp_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, cwd=PA_PROJECT_PATH
        )
        if result.returncode != 0:
            raise RuntimeError(f"Julia failed:\n{result.stderr}")
        return result.stdout
    finally:
        os.unlink(tmp_path)


def main():
    RESOURCES_DIR.mkdir(exist_ok=True)

    print("Generating API index...")
    api_index = run_julia_sync(API_INDEX_SCRIPT)
    (RESOURCES_DIR / "api_index.md").write_text(api_index)

    print("Generating component types...")
    comp_types = run_julia_sync(COMPONENT_TYPES_SCRIPT)
    (RESOURCES_DIR / "component_types.md").write_text(comp_types)

    # Count symbols
    symbol_count = api_index.count("\n- ")
    print(f"Done. {symbol_count} symbols indexed.")
    print(f"Files saved to {RESOURCES_DIR}/")


if __name__ == "__main__":
    main()
