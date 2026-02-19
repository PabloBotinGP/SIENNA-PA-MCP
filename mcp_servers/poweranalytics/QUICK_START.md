# PowerAnalytics MCP Server — Quick Start

## 1-Minute Setup

```bash
# Install dependencies
cd /Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run tests
pytest tests/ -v
```

## 1. Register in MCP Extension

Add to your editor's MCP config:

```json
{
  "poweranalytics": {
    "command": "python",
    "args": ["-m", "mcp.server.fastmcp", "path/to/main.py"],
    "env": {
      "PA_PROJECT_PATH": "/path/to/julia/project",
      "PA_RESULTS_DIR": "/path/to/results"
    }
  }
}
```

## 2. Start Server

MCP Extension → List Servers → poweranalytics → Start Server

## 3. Use from LLM Chat

```
"Get the generation time series for thermal components"
```

**Done!** The LLM will:
- Read the API reference resource
- Call get_active_power_timeseries() tool
- Explain the results

## Tools at a Glance

| Command | Use Case |
|---------|----------|
| `get_active_power_timeseries(...)` | Generation by component type (most common) |
| `check_julia_environment()` | Verify setup |
| `list_result_files(dir)` | Find results |
| `run_julia_script(code)` | Custom analysis |

## Common Prompts

```
"Get thermal generation time series"        → uses get_active_power_timeseries
"Compare scenarios"                          → uses run_julia_script + template
"What results do we have?"                   → uses list_result_files
"Check if Julia is installed"                → uses check_julia_environment
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Julia not found | Set `JULIA_EXECUTABLE=...` env var |
| PowerAnalytics not loaded | Install in Julia: `pkg> add PowerAnalytics` |
| Results not found | Check `PA_RESULTS_DIR` points to correct path |
| Script timeout | Increase `PA_SCRIPT_TIMEOUT` env var |

## What Happens Behind the Scenes

```
User: "Get thermal generation"
  ↓
LLM reads: poweranalytics://api-reference resource
  ↓
LLM calls: get_active_power_timeseries(component_type="ThermalStandard", ...)
  ↓
Server generates Julia script:
  - Load results
  - Create selector
  - Compute generation
  - Save CSV
  ↓
Server runs: julia --project=... script.jl
  ↓
Returns: DataFrame + stdout + stderr
  ↓
LLM explains: Generation patterns, MW values, insights
```

## For Developers

Add a new tool:

```python
@mcp.tool()
async def my_analysis(param1: str, param2: int) -> str:
    """What this tool does."""
    script = f"""
    # Julia code here
    println("result")
    """
    result = await _run_julia(script)
    return _format_result(result)
```

Then test:

```python
@pytest.mark.asyncio
async def test_my_analysis(monkeypatch):
    async def fake_run_julia(script, project_path=None):
        return {"exit_code": 0, "stdout": "output", "stderr": ""}

    monkeypatch.setattr(poweranalytics, "_run_julia", fake_run_julia)
    result = await poweranalytics.my_analysis("arg1", 42)
    assert "output" in result
```

## Documentation Links

- [README.md](README.md) — Full user guide
- [SETUP.md](SETUP.md) — Detailed configuration
- [DEMO.md](DEMO.md) — Example interactions
- [POWERANALYTICS_MCP_SUMMARY.md](../POWERANALYTICS_MCP_SUMMARY.md) — Architecture overview
