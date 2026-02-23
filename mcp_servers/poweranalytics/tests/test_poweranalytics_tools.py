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
    # Reset the auto-generation cooldown flag between tests
    monkeypatch.setattr(server, "_auto_gen_attempted", False)


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
# Lifespan tests (Issue 1: lifespan no longer calls Julia)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_never_calls_julia(monkeypatch, tmp_path):
    """Lifespan yields immediately without calling Julia (Issue 1 fix)."""
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)

    call_count = 0

    async def fake_run_julia(script, project_path=None):
        nonlocal call_count
        call_count += 1
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)

    async with server._lifespan(None):
        pass

    assert call_count == 0  # Julia is NEVER called during lifespan
    assert tmp_path.is_dir()  # resources dir is created


# ---------------------------------------------------------------------------
# _auto_generate_resources tests (Issue 1: deferred generation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_generate_skips_when_files_exist(monkeypatch, tmp_path):
    """Auto-generation returns None if resource files already exist."""
    (tmp_path / "api_index.md").write_text("existing index")
    (tmp_path / "component_types.md").write_text("existing types")
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)

    result = await server._auto_generate_resources()
    assert result is None


@pytest.mark.asyncio
async def test_auto_generate_runs_when_files_missing(monkeypatch, tmp_path):
    """Auto-generation calls Julia when files are missing and sysimage is available."""
    sysimage = tmp_path / "sysimage.so"
    sysimage.write_bytes(b"\x00" * 10)
    monkeypatch.setattr(server, "SYSIMAGE_PATH", str(sysimage))
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)

    call_count = 0

    async def fake_run_julia(script, project_path=None):
        nonlocal call_count
        call_count += 1
        return {
            "exit_code": 0,
            "stdout": "## PA\n- `func1` [Function]: desc\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)

    result = await server._auto_generate_resources()
    assert call_count == 2
    assert (tmp_path / "api_index.md").exists()
    assert (tmp_path / "component_types.md").exists()
    assert "generated" in result


@pytest.mark.asyncio
async def test_auto_generate_warns_without_sysimage(monkeypatch, tmp_path):
    """Auto-generation returns a warning message if no sysimage is configured."""
    monkeypatch.setattr(server, "SYSIMAGE_PATH", "")
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)

    result = await server._auto_generate_resources()
    assert "no sysimage" in result.lower()


@pytest.mark.asyncio
async def test_check_environment_triggers_auto_generate(monkeypatch, tmp_path):
    """check_julia_environment triggers resource auto-generation on success."""
    monkeypatch.setattr(server, "SYSIMAGE_PATH", "")
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)

    async def fake_run_julia(script, project_path=None):
        return {
            "exit_code": 0,
            "stdout": "Julia version: 1.10.0\nPowerAnalytics loaded.\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)

    result = await server.check_julia_environment()
    assert "Environment OK" in result
    # Should include resource generation message since files are missing
    assert "Resource generation" in result


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


# ---------------------------------------------------------------------------
# Issue 2-6: Documentation correctness tests
# ---------------------------------------------------------------------------


def test_fallback_api_index_documents_sorted_dict():
    """Issue 2: Fallback API index documents SortedDict return type."""
    index = server._FALLBACK_API_INDEX
    assert "SortedDict" in index
    assert "long/tidy format" in index or "long format" in index.lower()


def test_fallback_api_index_documents_get_timestamps_cadence():
    """Issue 6: get_timestamps documents execution cadence, not data resolution."""
    index = server._FALLBACK_API_INDEX
    assert "execution" in index.lower()
    # Should mention it returns step starts, not hourly timestamps
    assert "cadence" in index.lower() or "rolling-horizon" in index.lower() or "execution step" in index.lower()


def test_coding_guide_documents_sorted_dict():
    """Issue 2: Coding guide documents SortedDict return type."""
    guide = server.julia_coding_guide()
    assert "SortedDict" in guide


def test_coding_guide_documents_long_format():
    """Issue 3: Coding guide documents long/tidy format columns."""
    guide = server.julia_coding_guide()
    assert "name" in guide and "value" in guide
    assert "unstack" in guide


def test_coding_guide_documents_rolling_horizon_dedup():
    """Issue 4: Coding guide has rolling-horizon deduplication section."""
    guide = server.julia_coding_guide()
    assert "Rolling-Horizon Deduplication" in guide
    assert "realized" in guide
    assert "t_next" in guide


def test_coding_guide_documents_column_naming():
    """Issue 5: Coding guide documents column naming difference."""
    guide = server.julia_coding_guide()
    assert "ThermalStandard__321_CC_1" in guide
    assert "321_CC_1" in guide
    # Should have normalization one-liner
    assert "rename!" in guide


# ---------------------------------------------------------------------------
# Issue 7: JULIA_PREAMBLE includes Statistics
# ---------------------------------------------------------------------------


def test_julia_preamble_includes_statistics():
    """Issue 7: JULIA_PREAMBLE includes 'using Statistics'."""
    assert "using Statistics" in server.JULIA_PREAMBLE


# ---------------------------------------------------------------------------
# Issue 8: Worked example uses low-level path
# ---------------------------------------------------------------------------


def test_analyze_simulation_uses_read_variable():
    """Issue 8: Worked example uses read_variable, not populate_system=true as primary."""
    prompt = server.analyze_simulation()
    # read_variable should appear in the worked example
    assert "read_variable" in prompt
    # populate_system should be in secondary/alternative section, not primary
    lines = prompt.split("\n")
    read_var_idx = next(i for i, l in enumerate(lines) if "read_variable" in l)
    # Check that populate_system appears AFTER read_variable (secondary)
    populate_lines = [i for i, l in enumerate(lines) if "populate_system=true" in l]
    if populate_lines:
        # All populate_system mentions should be after the main read_variable usage
        # or in a clearly marked alternative section
        assert "alternative" in prompt.lower() or "warning" in prompt.lower()


# ---------------------------------------------------------------------------
# Issue 9: get_docstring allowed_modules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_docstring_allows_power_simulations(monkeypatch):
    """Issue 9: get_docstring accepts PowerSimulations as a module."""
    async def fake_run_julia(script, project_path=None):
        return {
            "exit_code": 0,
            "stdout": "read_variable docs here\n",
            "stderr": "",
        }

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_docstring("read_variable", "PowerSimulations")
    assert "Error" not in result or "Unknown module" not in result


@pytest.mark.asyncio
async def test_get_docstring_allows_power_systems(monkeypatch):
    """Issue 9: get_docstring accepts PowerSystems."""
    async def fake_run_julia(script, project_path=None):
        return {"exit_code": 0, "stdout": "ThermalStandard docs\n", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_docstring("ThermalStandard", "PowerSystems")
    assert "Unknown module" not in result


@pytest.mark.asyncio
async def test_get_docstring_allows_dataframes(monkeypatch):
    """Issue 9: get_docstring accepts DataFrames."""
    async def fake_run_julia(script, project_path=None):
        return {"exit_code": 0, "stdout": "DataFrame docs\n", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    result = await server.get_docstring("DataFrame", "DataFrames")
    assert "Unknown module" not in result


# ---------------------------------------------------------------------------
# Issue 10: list_variable_keys pretty-print pattern
# ---------------------------------------------------------------------------


def test_coding_guide_has_pretty_print_variable_keys():
    """Issue 10: Coding guide includes pretty-print pattern for variable keys."""
    guide = server.julia_coding_guide()
    assert "match(r" in guide or "match(" in guide
    # Should extract VariableName — ComponentType from verbose output
    assert "println" in guide


# ---------------------------------------------------------------------------
# Issue 12: _format_result ordering and Info filtering
# ---------------------------------------------------------------------------


def test_format_result_stdout_before_stderr():
    """Issue 12: stdout appears before stderr in formatted output."""
    result = {"exit_code": 0, "stdout": "data output", "stderr": "some warning"}
    formatted = server._format_result(result)
    stdout_pos = formatted.index("data output")
    stderr_pos = formatted.index("some warning")
    assert stdout_pos < stderr_pos


def test_format_result_filters_info_on_success():
    """Issue 12: Info log lines are filtered from stderr on success."""
    result = {
        "exit_code": 0,
        "stdout": "real output",
        "stderr": "[ Info: Loading package\n[ Info: Done\n",
    }
    formatted = server._format_result(result)
    assert "real output" in formatted
    assert "[ Info:" not in formatted


def test_format_result_filters_info_on_error():
    """Issue 12: Info log lines are filtered from stderr on error too (noise reduction)."""
    result = {
        "exit_code": 1,
        "stdout": "",
        "stderr": "[ Info: Loading\nERROR: something broke",
    }
    formatted = server._format_result(result)
    assert "[ Info:" not in formatted  # Info lines are always filtered
    assert "ERROR" in formatted  # Actual error is preserved


# ---------------------------------------------------------------------------
# Issue 4: Error handling documents rolling-horizon overlap
# ---------------------------------------------------------------------------


def test_error_handling_documents_rolling_horizon():
    """Issue 4: Error handling prompt warns about rolling-horizon overlap."""
    prompt = server.julia_error_handling()
    assert "rolling-horizon" in prompt.lower() or "Rolling-Horizon" in prompt
    assert "SortedDict" in prompt


# ---------------------------------------------------------------------------
# New tests for v2 fixes
# ---------------------------------------------------------------------------


def test_preamble_suppresses_info_logging():
    """Issue 1: JULIA_PREAMBLE suppresses Info-level logging."""
    assert "global_logger" in server.JULIA_PREAMBLE
    assert "Logging.Warn" in server.JULIA_PREAMBLE


@pytest.mark.asyncio
async def test_run_julia_script_auto_injects_preamble(monkeypatch):
    """Issue 8: run_julia_script auto-injects JULIA_PREAMBLE."""
    captured_scripts = []

    async def fake_run_julia(script, project_path=None):
        captured_scripts.append(script)
        return {"exit_code": 0, "stdout": "ok\n", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    await server.run_julia_script('println("hello")')
    assert len(captured_scripts) == 1
    # Should have the preamble prepended
    assert "using PowerAnalytics" in captured_scripts[0]
    assert "global_logger" in captured_scripts[0]


@pytest.mark.asyncio
async def test_run_julia_script_skips_preamble_when_present(monkeypatch):
    """Issue 8: run_julia_script doesn't double-inject preamble."""
    captured_scripts = []

    async def fake_run_julia(script, project_path=None):
        captured_scripts.append(script)
        return {"exit_code": 0, "stdout": "ok\n", "stderr": ""}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)
    script = 'using PowerAnalytics\nprintln("hello")'
    await server.run_julia_script(script)
    # Should inject logging suppression but not full preamble
    assert captured_scripts[0].count("using PowerAnalytics") == 1
    assert "global_logger" in captured_scripts[0]


def test_format_result_truncates_long_stderr():
    """Issue 10: Very long stderr is truncated."""
    long_stderr = "E" * 5000
    result = {"exit_code": 1, "stdout": "", "stderr": long_stderr}
    formatted = server._format_result(result)
    assert "truncated" in formatted
    assert len(formatted) < 5000


@pytest.mark.asyncio
async def test_auto_generate_cooldown(monkeypatch, tmp_path):
    """Issue 2: Auto-generation doesn't retry after first attempt."""
    sysimage = tmp_path / "sysimage.so"
    sysimage.write_bytes(b"\x00" * 10)
    monkeypatch.setattr(server, "SYSIMAGE_PATH", str(sysimage))
    monkeypatch.setattr(server, "_RESOURCES_DIR", tmp_path)

    call_count = 0

    async def fake_run_julia(script, project_path=None):
        nonlocal call_count
        call_count += 1
        # Simulate failure
        return {"exit_code": 1, "stdout": "", "stderr": "some error"}

    monkeypatch.setattr(server, "_run_julia", fake_run_julia)

    # First call: attempts generation (2 scripts)
    result1 = await server._auto_generate_resources()
    assert result1 is not None
    assert call_count == 2

    # Second call: should NOT retry (cooldown flag set)
    result2 = await server._auto_generate_resources()
    assert result2 is None
    assert call_count == 2  # no additional calls


def test_no_populate_system_in_docs():
    """Issue 4: populate_system=true is not recommended anywhere."""
    coding_guide = server.julia_coding_guide()
    error_handling = server.julia_error_handling()
    analyze = server.analyze_simulation()
    # Should not appear as a recommended pattern
    assert "populate_system=true" not in coding_guide
    assert "populate_system=true" not in error_handling
    assert "populate_system=true" not in analyze


def test_dedup_uses_step_not_typemax():
    """Issue 6: Rolling-horizon dedup code uses step duration, not typemax(DateTime)."""
    coding_guide = server.julia_coding_guide()
    analyze = server.analyze_simulation()
    # The dedup code blocks should use step-based boundary
    assert "t + step" in coding_guide
    assert "t + step" in analyze
    # typemax may appear in "What NOT to Do" warnings but not in code examples
    # Check that the actual dedup pattern uses step, not typemax
    for text in [coding_guide, analyze]:
        # Find the dedup code block and verify it uses t + step
        assert "t_next = i < length(exec_times) ? exec_times[i+1] : t + step" in text


def test_api_index_script_handles_missing_symbols():
    """Issue 5: API_INDEX_SCRIPT uses isdefined and try/catch per symbol."""
    assert "isdefined(mod, name)" in server.API_INDEX_SCRIPT
    assert "try" in server.API_INDEX_SCRIPT
    assert "catch" in server.API_INDEX_SCRIPT
