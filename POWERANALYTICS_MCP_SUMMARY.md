# PowerAnalytics MCP Server — Implementation Summary

## What Was Built

A complete MCP (Model Context Protocol) server that enables Claude to interact with PowerAnalytics.jl — a Julia package for analyzing power system simulation results.

**Location:** `/Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics/`

## Architecture

### Design Approach (Option C + B from earlier discussion)

1. **High-level tools** (Option C) — LLM passes parameters, tool generates Julia script internally
   - Reduces hallucination risk
   - Ensures correct API usage

2. **Template prompts** (Option B) — Guide the LLM for standard analyses
   - Provide workflow templates
   - Show best practices

3. **Escape hatch** (Option A) — `run_julia_script` for custom analysis
   - Used when high-level tools don't cover the use case
   - Requires reading resources first

### Key Decision: No Remote API

- PowerAnalytics.jl runs **locally** via subprocess (not HTTP)
- Each tool call executes Julia with `julia --project=...` + a temp script file
- Results return to the LLM via stdout/stderr
- Configuration via environment variables: `JULIA_EXECUTABLE`, `PA_PROJECT_PATH`, `PA_RESULTS_DIR`, `PA_SCRIPT_TIMEOUT`

## File Structure

```
mcp_servers/poweranalytics/
├── server.py           # Main server (tools, resources, prompts)
├── main.py                      # Entry point for MCP extension
├── pyproject.toml               # Python dependencies + pytest config
├── .python-version              # Python 3.11
├── README.md                    # User guide
├── SETUP.md                     # How to register and start the server
├── DEMO.md                      # Example interactions with the LLM
└── tests/
    └── test_poweranalytics_tools.py  # 15 unit tests (all passing)
```

## Tools (4)

| Tool | Purpose | Type |
|------|---------|------|
| `run_julia_script(script, project_path)` | Execute arbitrary Julia code | Escape hatch |
| `check_julia_environment(project_path)` | Verify Julia + PowerAnalytics.jl are available | Diagnostic |
| `get_active_power_timeseries(...)` | Get generation time series for a component type (high-level) | Option C |
| `list_result_files(directory, pattern)` | Discover saved results and output files | Utility |

### Example Tool Call

```python
# LLM calls:
get_active_power_timeseries(
    results_dir="_simulation_results_RTS",
    problem_name="UC",
    component_type="ThermalStandard",
    output_csv="results/thermal_output.csv"
)

# Tool generates and executes:
using PowerAnalytics, PowerSystems, DataFrames, CSV
results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
selector = make_selector(ThermalStandard)
df = calc_active_power(selector, results_all["Scenario_1"])
CSV.write("results/thermal_output.csv", df)

# Returns: DataFrame with generation by thermal unit + stdout
```

## Resources (2)

| URI | Content |
|-----|---------|
| `poweranalytics://api-reference` | PowerAnalytics.jl API reference — function signatures, usage patterns, required packages |
| `poweranalytics://component-types` | PowerSystems.jl component types, formulations, and available result variables |

**Why resources matter:** The LLM reads these before writing custom Julia code, preventing hallucination of non-existent functions.

## Prompts (2)

| Prompt | Template |
|--------|----------|
| `analyze_generation(component_type, results_dir, problem_name)` | Guide for analyzing generation time series by component type |
| `compare_scenarios(component_type, results_dir, problem_name)` | Template for cross-scenario comparison analysis |

**Why prompts matter:** They show the LLM the correct workflow and standard conventions.

## Configuration

Set via environment variables (or edit constants in `server.py`):

```bash
export JULIA_EXECUTABLE="julia"                     # Path to Julia binary
export PA_PROJECT_PATH="/path/to/julia/project"    # Project with PowerAnalytics.jl
export PA_RESULTS_DIR="/path/to/results"           # Simulation results directory
export PA_SCRIPT_TIMEOUT="300"                     # Max seconds for Julia scripts
```

## Testing

**15 unit tests**, all passing:

```bash
cd mcp_servers/poweranalytics
.venv/bin/pytest tests/ -v
```

Test coverage:
- Tool execution with mocked Julia subprocess
- Resource content validation
- Prompt template generation
- Error handling (timeouts, missing files, failed scripts)
- File listing with glob patterns

## How to Use

### 1. Register the server

In your MCP extension configuration (`~/.mcp/config.json` or editor settings):

```json
{
  "servers": {
    "poweranalytics": {
      "command": "python",
      "args": [
        "-m",
        "mcp.server.fastmcp",
        "/path/to/mcp_servers/poweranalytics/main.py"
      ],
      "env": {
        "PA_PROJECT_PATH": "/path/to/julia/project",
        "PA_RESULTS_DIR": "/path/to/simulation/results"
      }
    }
  }
}
```

### 2. Start the server

- Open MCP extension → **List Servers** → **poweranalytics** → **Start Server**

### 3. Ask the LLM

```
"Obtain the generation time series for each individual thermal component of the system"
```

**What happens:**
1. LLM reads `poweranalytics://api-reference` resource
2. LLM calls `get_active_power_timeseries(component_type="ThermalStandard", ...)`
3. Server generates + executes Julia script, returns results
4. LLM reads the DataFrame and explains it to you in context of power system operations

## Example Interaction

**User:** "How did the increased storage capacity in Scenario 2 affect thermal generation?"

**LLM:**
1. Reads `analyze_generation` prompt
2. Calls `run_julia_script` with custom script that compares both scenarios
3. Analyzes output: "Storage displaced ~250 MW of thermal generation on average"
4. Explains economic impact: "Lower operating costs, improved dispatch efficiency"

See [DEMO.md](DEMO.md) for full interactions.

## Next Steps

### To Add More Tools

1. Create a new `@mcp.tool()` function in `server.py`
2. Generate Julia script internally (don't make LLM write it)
3. Add test in `tests/test_poweranalytics_tools.py`
4. Run: `.venv/bin/pytest tests/ -v`

### Examples of Future Tools

```python
@mcp.tool()
async def get_generation_by_fuel_type(scenario, results_dir, output_csv=None):
    """Aggregate generation by fuel type (coal, gas, nuclear, renewable)"""
    # Script: filter by fuel type, sum generation

@mcp.tool()
async def get_storage_dispatch(results_dir, scenario, storage_id=None):
    """Get energy storage charging/discharging schedule"""
    # Script: select EnergyReservoirStorage or EnergyReservoirStorage, get results

@mcp.tool()
async def compute_system_cost(results_dir, scenario):
    """Calculate total production cost"""
    # Script: sum across all cost expressions in results
```

## Documentation

- **README.md** — User guide, tool/resource/prompt summary
- **SETUP.md** — Registration and configuration instructions
- **DEMO.md** — Realistic interaction examples
- **server.py** — Docstrings for all tools/resources/prompts

## Dependencies

- `mcp[cli]>=1.26.0` — MCP framework
- `pytest>=7.0.0` — Testing
- `pytest-asyncio>=0.21.0` — Async test support

Python 3.11+ required.

## Status

✅ **Complete and tested**

- All 4 tools implemented
- All 2 resources implemented
- All 2 prompts implemented
- 15 unit tests passing
- Documentation complete
