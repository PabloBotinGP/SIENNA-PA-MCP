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
# get_docstring tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_docstring_success(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {
            "exit_code": 0,
            "stdout": "calc_active_power(selector, results)\n\nCompute active power.\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_docstring("calc_active_power", "PowerAnalytics.Metrics")
    assert "calc_active_power" in result
    assert "Compute active power" in result


@pytest.mark.asyncio
async def test_get_docstring_invalid_symbol():
    result = await server.get_docstring("not-valid!", "PowerAnalytics")
    assert "Error" in result
    assert "Invalid symbol name" in result


@pytest.mark.asyncio
async def test_get_docstring_invalid_module():
    result = await server.get_docstring("calc_active_power", "SomeRandomModule")
    assert "Error" in result
    assert "Unknown module" in result


@pytest.mark.asyncio
async def test_get_docstring_not_found(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {
            "exit_code": 0,
            "stdout": "Symbol 'nonexistent_func' not found in PowerAnalytics\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_docstring("nonexistent_func", "PowerAnalytics")
    assert "not found" in result


# ---------------------------------------------------------------------------
# refresh_api_index tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_api_index(monkeypatch, tmp_path):
    call_count = 0

    async def fake_run_julia(script, project_path=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # API index script
            return {
                "exit_code": 0,
                "stdout": "## PowerAnalytics\n- `func1` [Function]: Does stuff\n- `func2` [Function]: More stuff\n",
                "stderr": "",
            }
        else:
            # Component types script
            return {
                "exit_code": 0,
                "stdout": "## Generators\n- `ThermalStandard`\n",
                "stderr": "",
            }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)
    result = await server.refresh_api_index()
    assert "refreshed" in result
    assert "2 symbols" in result
    assert (tmp_path / "api_index.md").exists()
    assert (tmp_path / "component_types.md").exists()


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


def test_api_index_resource(tmp_path, monkeypatch):
    """API index resource reads from file when available."""
    resources_dir = tmp_path / "resources"
    resources_dir.mkdir()
    (resources_dir / "api_index.md").write_text("## PowerAnalytics\n- `func1` [Function]: test\n")
    monkeypatch.setattr(server, "_RESOURCES_DIR", resources_dir)
    content = server.get_api_index()
    assert "func1" in content


def test_api_index_resource_fallback(monkeypatch):
    """API index resource falls back to hardcoded text when file missing."""
    monkeypatch.setattr(server, "_RESOURCES_DIR", Path("/nonexistent/path"))
    content = server.get_api_index()
    assert "create_problem_results_dict" in content
    assert "fallback" in content.lower()


def test_component_types_resource(tmp_path, monkeypatch):
    """Component types resource reads from file when available."""
    resources_dir = tmp_path / "resources"
    resources_dir.mkdir()
    (resources_dir / "component_types.md").write_text("## Generators\n- `ThermalStandard`\n")
    monkeypatch.setattr(server, "_RESOURCES_DIR", resources_dir)
    content = server.get_component_types()
    assert "ThermalStandard" in content


def test_component_types_resource_fallback(monkeypatch):
    """Component types resource falls back to hardcoded text when file missing."""
    monkeypatch.setattr(server, "_RESOURCES_DIR", Path("/nonexistent/path"))
    content = server.get_component_types()
    assert "ThermalStandard" in content
    assert "fallback" in content.lower()


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_analyze_simulation_prompt():
    prompt = server.analyze_simulation(
        task_description="Analyze thermal generation",
        results_dir="_simulation_results_RTS",
        problem_name="UC",
    )
    assert "Analyze thermal generation" in prompt
    assert "7-Step Workflow" in prompt
    assert "check_julia_environment" in prompt
    assert "get_docstring" in prompt
    assert "run_julia_script" in prompt
    assert "julia_coding_guide" in prompt
    assert "julia_error_handling" in prompt
    assert "results_presentation" in prompt
    assert "_simulation_results_RTS" in prompt


def test_julia_coding_guide_prompt():
    prompt = server.julia_coding_guide()
    assert "using PowerAnalytics" in prompt
    assert "DataFrame" in prompt
    assert "preamble" in prompt.lower()
    assert "do NOT" in prompt.lower() or "What NOT to Do" in prompt


def test_julia_error_handling_prompt():
    prompt = server.julia_error_handling()
    assert "MethodError" in prompt
    assert "retry" in prompt.lower() or "3" in prompt
    assert "LoadError" in prompt or "UndefVarError" in prompt


def test_output_saving_conventions_prompt():
    prompt = server.output_saving_conventions(results_dir="_simulation_results_RTS")
    assert "_simulation_results_RTS" in prompt
    assert "csv" in prompt.lower()
    assert "Naming Convention" in prompt or "naming" in prompt.lower()


def test_results_presentation_prompt():
    prompt = server.results_presentation()
    assert "MW" in prompt
    assert "MWh" in prompt
    assert "units" in prompt.lower()
    assert "summary" in prompt.lower() or "summariz" in prompt.lower()


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
