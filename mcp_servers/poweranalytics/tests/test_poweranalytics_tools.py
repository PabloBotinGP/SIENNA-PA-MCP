import os
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import mcp_servers.poweranalytics.server as server


# ---------------------------------------------------------------------------
# Helper to run async tools
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_project_path(tmp_path, monkeypatch):
    """Point PA_PROJECT_PATH to a temp dir for all tests."""
    monkeypatch.setattr(server, "PA_PROJECT_PATH", tmp_path)
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)


# ---------------------------------------------------------------------------
# _run_julia tests (mock the subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_julia_script_success(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {"exit_code": 0, "stdout": "hello from julia\n", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.run_julia_script('println("hello from julia")')
    assert "hello from julia" in result


@pytest.mark.asyncio
async def test_run_julia_script_failure(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {"exit_code": 1, "stdout": "", "stderr": "ERROR: LoadError"}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.run_julia_script("bad code")
    assert "ERROR" in result
    assert "Exit code: 1" in result


# ---------------------------------------------------------------------------
# check_julia_environment tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_environment_ok(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {
            "exit_code": 0,
            "stdout": "Julia version: 1.10.0\nPowerAnalytics loaded successfully.\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.check_julia_environment()
    assert "Environment OK" in result
    assert "PowerAnalytics loaded" in result


@pytest.mark.asyncio
async def test_check_environment_fail(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": "Package PowerAnalytics not found",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.check_julia_environment()
    assert "FAILED" in result


# ---------------------------------------------------------------------------
# get_active_power_timeseries tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_power_timeseries_generates_correct_script(monkeypatch):
    captured_scripts = []

    async def fake_run_julia(script, project_path=None):
        captured_scripts.append(script)
        return {"exit_code": 0, "stdout": "Shape: (744, 77)\n", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_active_power_timeseries(
        results_dir="_simulation_results_RTS",
        problem_name="UC",
        component_type="ThermalStandard",
        scenario="Scenario_1",
    )
    assert "Shape:" in result
    script = captured_scripts[0]
    assert "create_problem_results_dict" in script
    assert "ThermalStandard" in script
    assert "calc_active_power" in script
    assert 'results_all["Scenario_1"]' in script


@pytest.mark.asyncio
async def test_get_active_power_timeseries_with_csv(monkeypatch):
    captured_scripts = []

    async def fake_run_julia(script, project_path=None):
        captured_scripts.append(script)
        return {
            "exit_code": 0,
            "stdout": "Results saved to output.csv\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_active_power_timeseries(
        results_dir="_results",
        problem_name="UC",
        component_type="RenewableDispatch",
        output_csv="output.csv",
    )
    assert "CSV.write" in captured_scripts[0]
    assert "saved to output.csv" in result


# ---------------------------------------------------------------------------
# list_result_files tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_result_files(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "results.h5").write_bytes(b"\x00" * 100)
    result = await server.list_result_files(str(tmp_path))
    assert "data.csv" in result
    assert "results.h5" in result


@pytest.mark.asyncio
async def test_list_result_files_not_found():
    result = await server.list_result_files("/nonexistent/path")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_list_result_files_with_pattern(tmp_path):
    (tmp_path / "a.csv").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    result = await server.list_result_files(str(tmp_path), pattern="*.csv")
    assert "a.csv" in result
    assert "b.txt" not in result


# ---------------------------------------------------------------------------
# Resource tests
# ---------------------------------------------------------------------------


def test_api_reference_resource():
    content = server.get_api_reference()
    assert "create_problem_results_dict" in content
    assert "make_selector" in content
    assert "calc_active_power" in content


def test_component_types_resource():
    content = server.get_component_types()
    assert "ThermalStandard" in content
    assert "EnergyReservoirStorage" in content


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_analyze_generation_prompt():
    prompt = server.analyze_generation(component_type="HydroDispatch")
    assert "HydroDispatch" in prompt
    assert "get_active_power_timeseries" in prompt


def test_compare_scenarios_prompt():
    prompt = server.compare_scenarios(component_type="EnergyReservoirStorage")
    assert "EnergyReservoirStorage" in prompt
    assert "create_problem_results_dict" in prompt


# ---------------------------------------------------------------------------
# _format_result tests
# ---------------------------------------------------------------------------


def test_format_result_success():
    result = {"exit_code": 0, "stdout": "output here", "stderr": ""}
    formatted = server._format_result(result)
    assert "output here" in formatted
    assert "Exit code" not in formatted


def test_format_result_error():
    result = {"exit_code": 1, "stdout": "", "stderr": "some error"}
    formatted = server._format_result(result)
    assert "Exit code: 1" in formatted
    assert "some error" in formatted


# ---------------------------------------------------------------------------
# Sysimage configuration tests
# ---------------------------------------------------------------------------


def test_sysimage_path_default():
    """PA_SYSIMAGE_PATH defaults to empty string (no sysimage)."""
    assert hasattr(server, "SYSIMAGE_PATH")
    # default is empty when env var is not set
    assert isinstance(server.SYSIMAGE_PATH, str)


@pytest.mark.asyncio
async def test_run_julia_uses_sysimage_when_available(monkeypatch, tmp_path):
    """When SYSIMAGE_PATH points to an existing file, --sysimage is added."""
    sysimage_file = tmp_path / "pa_sysimage.so"
    sysimage_file.write_bytes(b"\x00" * 10)  # fake file
    monkeypatch.setattr(server, "SYSIMAGE_PATH", str(sysimage_file))

    captured_cmds = []

    original_exec = asyncio.create_subprocess_exec

    async def capture_exec(*args, **kwargs):
        captured_cmds.append(list(args))
        # Return a mock process
        proc = MagicMock()
        proc.returncode = 0

        async def communicate():
            return (b"ok\n", b"")

        proc.communicate = communicate
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_exec)
    monkeypatch.setattr(server, "PA_PROJECT_PATH", tmp_path)

    await server._run_julia("println(1)")
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert any(f"--sysimage={sysimage_file}" in str(a) for a in cmd), (
        f"Expected --sysimage flag in command: {cmd}"
    )


@pytest.mark.asyncio
async def test_run_julia_skips_sysimage_when_missing(monkeypatch, tmp_path):
    """When SYSIMAGE_PATH is empty or file doesn't exist, --sysimage is NOT added."""
    monkeypatch.setattr(server, "SYSIMAGE_PATH", "")

    captured_cmds = []

    async def capture_exec(*args, **kwargs):
        captured_cmds.append(list(args))
        proc = MagicMock()
        proc.returncode = 0

        async def communicate():
            return (b"ok\n", b"")

        proc.communicate = communicate
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_exec)
    monkeypatch.setattr(server, "PA_PROJECT_PATH", tmp_path)

    await server._run_julia("println(1)")
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert not any("--sysimage" in str(a) for a in cmd), (
        f"Did NOT expect --sysimage flag in command: {cmd}"
    )
