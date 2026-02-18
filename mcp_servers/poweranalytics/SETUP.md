# PowerAnalytics MCP Server — Setup Guide

This guide explains how to register and use the PowerAnalytics MCP server in your editor's MCP extension.

## Prerequisites

1. **Julia** installed and on PATH (or set `JULIA_EXECUTABLE` environment variable)
2. **PowerAnalytics.jl** and dependencies installed in a Julia project:
   ```bash
   julia -e 'using Pkg; Pkg.add(["PowerAnalytics", "PowerSystems", "PowerSimulations", "StorageSystemsSimulations", "HydroPowerSimulations"])'
   ```
3. **Simulation results** directory with results from PowerSimulations.jl
4. **MCP CLI** installed: `pip install mcp[cli]` or `uv pip install mcp[cli]`

## 1. Register the Server in MCP

The server entry point is `poweranalytics:main` (from `main.py`).

Add the following to your MCP configuration file (usually `~/.mcp/config.json` or set in your editor's MCP extension):

```json
{
  "servers": {
    "poweranalytics": {
      "command": "python",
      "args": [
        "-m",
        "mcp.server.fastmcp",
        "/Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics/main.py"
      ],
      "env": {
        "JULIA_EXECUTABLE": "julia",
        "PA_PROJECT_PATH": "/path/to/your/julia/project",
        "PA_RESULTS_DIR": "/path/to/simulation/results",
        "PA_SCRIPT_TIMEOUT": "300"
      }
    }
  }
}
```

### Configuration via Environment Variables

The server uses these environment variables (or defaults):

| Variable | Default | What it controls |
|----------|---------|------------------|
| `JULIA_EXECUTABLE` | `julia` | Path to Julia binary |
| `PA_PROJECT_PATH` | `.` | Julia project containing PowerAnalytics.jl |
| `PA_RESULTS_DIR` | `.` | Default directory for simulation results |
| `PA_SCRIPT_TIMEOUT` | `300` | Max seconds for Julia scripts to run |

## 2. Start the Server

### Option A: Via MCP Extension in Your Editor

1. Open your editor (VS Code with Anthropic Claude Code, or compatible)
2. Go to **MCP: List Servers**
3. Find **poweranalytics** in the list
4. Click **Start Server**
5. You should see a green checkmark when it's ready

### Option B: Manually via CLI

```bash
cd /Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics
.venv/bin/python main.py
```

## 3. Use the Server from the LLM Chat

Once the server is running, you can ask the LLM to analyze simulation results. Examples:

### Example 1: Get thermal generation time series

**You:** "Get the generation time series for each thermal component in the system."

**LLM does:**
- Reads `poweranalytics://api-reference` resource
- Calls `get_active_power_timeseries(results_dir, problem_name="UC", component_type="ThermalStandard")`
- Returns a DataFrame with generation by thermal unit
- Explains the results (MW values, generation patterns, baseload vs peaking behavior)

### Example 2: Compare scenarios

**You:** "Compare total generation across the two simulation scenarios."

**LLM does:**
- Uses the `compare_scenarios` prompt template
- Calls `run_julia_script` with a custom script that loads both scenarios
- Computes total generation per timestep for each
- Returns comparison and insights

### Example 3: Explore results

**You:** "What result files do we have available?"

**LLM does:**
- Calls `list_result_files(directory, pattern="*")`
- Shows all discoverable simulation results

## 4. Troubleshooting

### Server won't start

- **Julia not found:** Verify Julia is on PATH: `julia --version`
- **PowerAnalytics not installed:** `julia -e 'using PowerAnalytics'` should not error
- **Project path incorrect:** Check `PA_PROJECT_PATH` points to a valid Julia project with a `Project.toml`

### Tools return errors

- **"Unable to load results":** Make sure `PA_RESULTS_DIR` points to the correct simulation output directory
- **Script timeout:** Increase `PA_SCRIPT_TIMEOUT` if working with large datasets
- **Julia syntax errors:** The LLM may have made a mistake. The error will be in the tool output. Ask the LLM to fix it.

### Check the environment

Use the `check_julia_environment` tool:

**You:** "Check if the Julia environment is set up correctly."

**LLM does:**
- Calls `check_julia_environment()`
- Reports Julia version, PowerAnalytics loaded status, active project

## 5. Testing

Run the test suite to verify everything works:

```bash
cd /Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics
.venv/bin/pytest tests/ -v
```

All 15 tests should pass.
