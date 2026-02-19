# PowerAnalytics MCP Server

A comprehensive MCP (Model Context Protocol) server that enables Claude to interact with **PowerAnalytics.jl** — a Julia package for analyzing power system simulation results locally.

## Overview

This repository contains the PowerAnalytics MCP server, which exposes:

- **4 Tools** — Generate and execute Julia scripts, check environment, discover results
- **2 Resources** — API reference and component type documentation
- **2 Prompts** — Analysis workflow templates

## Quick Start

1. **Register the server** in your MCP extension:
   ```json
   {
     "poweranalytics": {
       "command": "python",
       "args": ["-m", "mcp.server.fastmcp", "path/to/main.py"],
       "env": {
         "PA_PROJECT_PATH": "/path/to/julia/project",
         "PA_RESULTS_DIR": "/path/to/simulation/results"
       }
     }
   }
   ```

2. **Start the server** via MCP extension: List Servers → poweranalytics → Start Server

3. **Ask Claude**:
   ```
   "Obtain the generation time series for each thermal component"
   ```

## What PowerAnalytics.jl Does

PowerAnalytics.jl is a Julia package for analyzing power system simulation results from PowerSimulations.jl. It provides:

- Extracting generation, costs, and power flows by component type
- Aggregating results across time periods, regions, or asset categories
- Computing metrics and analyzing system behavior
- Preparing data for visualization and reporting

## Architecture

**No remote API calls** — PowerAnalytics runs locally via Julia subprocess.

**Three levels of tools:**

| Level | Tool | Type | Use Case |
|-------|------|------|----------|
| High-level | `get_active_power_timeseries` | Option C | Generation by component type |
| Escape hatch | `run_julia_script` | Raw Julia | Custom analysis |
| Utility | `check_julia_environment`, `list_result_files` | Diagnostic | Setup & discovery |

**Resources** prevent hallucination:
- `poweranalytics://api-reference` — PowerAnalytics.jl API documentation
- `poweranalytics://component-types` — Available types and formulations

**Prompts** guide workflows:
- `analyze_generation` — Generation time series analysis template
- `compare_scenarios` — Cross-scenario comparison template

## Project Layout

```
mcp_servers/poweranalytics/
├── server.py                      # Main server
├── main.py                         # MCP entry point
├── pyproject.toml                  # Dependencies
├── README.md                       # Full user guide
├── SETUP.md                        # Configuration instructions
├── DEMO.md                         # Example interactions
├── QUICK_START.md                  # Quick reference
└── tests/
    └── test_poweranalytics_tools.py  # 15 unit tests
```

## Usage Examples

### Example 1: Get thermal generation
```
User: "Get the generation time series for each thermal component"

LLM:
- Reads poweranalytics://api-reference
- Calls get_active_power_timeseries(component_type="ThermalStandard", ...)
- Explains: "76 thermal units, baseload nuclear at 400 MW, peakers cycle..."
```

### Example 2: Compare scenarios
```
User: "How did storage capacity affect generation in Scenario 2?"

LLM:
- Uses compare_scenarios prompt
- Calls run_julia_script with cross-scenario comparison
- Explains: "Storage displaced ~250 MW of thermal generation on average"
```

## Configuration

Set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `JULIA_EXECUTABLE` | `julia` | Path to Julia binary |
| `PA_PROJECT_PATH` | `.` | Julia project with PowerAnalytics.jl |
| `PA_RESULTS_DIR` | `.` | Simulation results directory |
| `PA_SCRIPT_TIMEOUT` | `300` | Max seconds per Julia script |
| `PA_SYSIMAGE_PATH` | *(empty)* | Optional precompiled sysimage path |

## Testing

```bash
cd mcp_servers/poweranalytics
pytest tests/ -v
```

All 15 tests pass ✓

## Documentation

- **[QUICK_START.md](mcp_servers/poweranalytics/QUICK_START.md)** — 1-minute overview
- **[README.md](mcp_servers/poweranalytics/README.md)** — Complete user guide
- **[SETUP.md](mcp_servers/poweranalytics/SETUP.md)** — Installation & configuration
- **[DEMO.md](mcp_servers/poweranalytics/DEMO.md)** — Example interactions

## Status

✅ **Production ready** — All tools, resources, and prompts implemented and tested.
