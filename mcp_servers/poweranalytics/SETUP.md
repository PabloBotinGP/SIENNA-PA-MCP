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

## 1. Generate the API Index

After installing PowerAnalytics.jl, generate the API index files:

```bash
cd /path/to/SIENNA-PA-MCP/mcp_servers/poweranalytics
python generate_index.py
```

This creates `resources/api_index.md` and `resources/component_types.md` from the
installed Julia packages. If you skip this step, the server will use a static fallback
with a reduced set of symbols.

## 2. Register the Server in MCP

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
| `PA_SYSIMAGE_PATH` | *(empty)* | Optional precompiled Julia sysimage |

## 3. Start the Server

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

## 4. Use the Server from the LLM Chat

Once the server is running, the LLM follows a 7-step agentic workflow:

1. **Check environment** — `check_julia_environment()`
2. **Read API index** — `poweranalytics://api-index` resource
3. **Read component types** — `poweranalytics://component-types` resource
4. **Get docstrings** — `get_docstring(symbol, module)` for relevant functions
5. **Write & execute** — `run_julia_script(script)` with composed Julia code
6. **Save results** — CSV files with descriptive names
7. **Present analysis** — summarize with units and power systems context

### Example: Thermal generation analysis

**You:** "Get the thermal generation time series for the RTS system."

**LLM does:**
- Reads API index, finds `calc_active_power` and `make_selector`
- Gets docstrings for those functions
- Writes a Julia script using `ThermalStandard` component type
- Executes the script, saves results to CSV
- Presents a summary with MW values and generation patterns

### Example: Discover results

**You:** "What result files do we have available?"

**LLM does:**
- Calls `list_result_files(directory, pattern="*")`
- Shows all discoverable simulation results

## 5. Troubleshooting

### Server won't start

- **Julia not found:** Verify Julia is on PATH: `julia --version`
- **PowerAnalytics not installed:** `julia -e 'using PowerAnalytics'` should not error
- **Project path incorrect:** Check `PA_PROJECT_PATH` points to a valid Julia project with a `Project.toml`

### Tools return errors

- **"Unable to load results":** Make sure `PA_RESULTS_DIR` points to the correct simulation output directory
- **Script timeout:** Increase `PA_SCRIPT_TIMEOUT` if working with large datasets
- **Julia syntax errors:** The LLM reads the error, fixes the script, and retries (up to 3 times)

### Check the environment

Use the `check_julia_environment` tool:

**You:** "Check if the Julia environment is set up correctly."

**LLM does:**
- Calls `check_julia_environment()`
- Reports Julia version, PowerAnalytics loaded status, active project

### Refresh the API index

If you've updated PowerAnalytics.jl mid-session:

**You:** "Refresh the API index."

**LLM does:**
- Calls `refresh_api_index()`
- Regenerates `resources/api_index.md` and `resources/component_types.md`

## 6. Testing

Run the test suite to verify everything works:

```bash
cd /Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics
PYTHONPATH=/Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP .venv/bin/pytest tests/ -v
```

All 26 tests should pass.
