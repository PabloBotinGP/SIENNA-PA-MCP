# Implementation Plan: Dynamic Agentic PowerAnalytics MCP Server

## Context

The current MCP server has hardcoded tools (like `get_active_power_timeseries`) and static resources (hand-written API reference strings). This means every new analysis task requires a new tool to be coded. PowerAnalytics.jl actually exports **39 symbols**, **25 built-in metrics**, and **8 built-in selectors** — but the server only exposes one metric through one tool.

The redesign replaces this with a dynamic "index → docstring → generate → execute" workflow. The LLM discovers the API at runtime, pulls detailed docs on demand, writes its own Julia scripts, and executes them. No new Python code needed for new analysis tasks.

## Architecture: Before → After

| Aspect | Current | New |
|--------|---------|-----|
| Tools | 4 (one hardcoded per-task) | 5 (generic, reusable) |
| Resources | 2 (static strings) | 2 (auto-generated from Julia) |
| Prompts | 2 (task-specific templates) | 5 (master + 4 specialized sub-prompts) |
| Adding new analysis | Write new Python tool | LLM figures it out from docs |

## Key Design Decisions

1. **API index generated once, saved to files** — Run `python generate_index.py` once after installing/updating PowerAnalytics.jl. Output saved to `resources/*.md`. Server reads from disk (instant startup, no Julia needed). `refresh_api_index` tool for mid-session updates.

2. **`get_docstring` as a tool, not a resource template** — Resource templates aren't reliably called by all MCP clients. A tool is universally callable. Cost: ~2-3s per call with sysimage, but LLM typically needs 1-3 docstrings per task.

3. **Remove `get_active_power_timeseries`** — It's the exact pattern the new architecture eliminates. The worked example in the orchestration prompt shows how the LLM achieves the same result dynamically.

4. **Persistent Julia REPL deferred** — Sysimage already brings latency to 2-3s/call. A persistent REPL adds complexity (process lifecycle, state isolation, crash recovery) for marginal gain. Revisit if latency becomes a pain point.

5. **Fallback to current hardcoded text** — If Julia fails at startup, the old static text is used as fallback so the server still works.

---

## Implementation Phases

### Phase 1: Index generation script + file-based resources

**New file: `generate_index.py`**

Standalone script that:
1. Runs two Julia subprocesses (can run in parallel):
   - **API index script**: Iterates `names(PowerAnalytics)`, `names(PowerAnalytics.Metrics)`, `names(PowerAnalytics.Selectors)` and extracts first-line docstrings via `Base.doc()`
   - **Component types script**: Uses `subtypes()` to enumerate PowerSystems.jl concrete component types
2. Saves output to:
   - `resources/api_index.md` — one-line-per-symbol index of all exports
   - `resources/component_types.md` — component type hierarchy
3. Prints summary (symbol count, file sizes)

Usage: `python generate_index.py` (run once after installing/updating PowerAnalytics.jl)

**File: `server.py`**

- Add `_RESOURCES_DIR = Path(__file__).parent / "resources"` constant
- Replace `get_api_reference()` → `get_api_index()` which reads `resources/api_index.md` from disk
- Replace `get_component_types()` which reads `resources/component_types.md` from disk
- If files don't exist: fall back to hardcoded `_FALLBACK_API_INDEX` / `_FALLBACK_COMPONENT_TYPES` strings and log a warning
- No `lifespan` hook needed — file reads are instant, no Julia at startup

### Phase 2: `get_docstring` tool
**File: `server.py`**

- New `get_docstring(symbol_name, module_name="PowerAnalytics")` tool
- Input validation: `symbol_name.isidentifier()` check, `module_name` whitelist (`PowerAnalytics`, `PowerAnalytics.Metrics`, `PowerAnalytics.Selectors`)
- Generates Julia script: `Base.doc(getfield(module, Symbol(name)))`
- Returns full docstring text or clear error message

### Phase 3: `refresh_api_index` tool
**File: `server.py`**

- New `refresh_api_index()` tool — runs the same Julia scripts as `generate_index.py`, overwrites the `resources/*.md` files, reloads the in-memory content, returns symbol count
- This is the "update without restarting the server" escape hatch

### Phase 4: Prompt system — master orchestrator + 4 specialized sub-prompts
**File: `server.py`**

- **Delete** `get_active_power_timeseries` function entirely
- **Delete** `analyze_generation` and `compare_scenarios` prompts
- **Update** `instructions` in `FastMCP(...)` to describe the new workflow

**Add 5 prompts:**

#### 4a. `analyze_simulation` — Master orchestration prompt
Parameters: `task_description`, `results_dir`, `problem_name`

The entry point. Teaches the 7-step workflow:
1. Check environment
2. Read API index
3. Read component types
4. Get docstrings for relevant functions
5. Write and execute Julia script (→ references `julia_coding_guide` prompt)
6. Save results (→ references `output_saving_conventions` prompt)
7. Analyze and present (→ references `results_presentation` prompt)

Includes a complete worked example (thermal generation analysis) and references
the sub-prompts by name so the LLM knows to read them when it reaches each step.

#### 4b. `julia_coding_guide` — Julia code generation best practices
No parameters (static guidance).

Covers:
- Required imports (the standard preamble)
- How to structure scripts: load results → create selectors → compute metrics → output
- DataFrame conventions: first column is DateTime, data columns are components
- Type system: when to use `ThermalStandard` vs `ThermalGen` (concrete vs abstract)
- Common patterns: iterating scenarios, filtering components, aggregating across time
- What NOT to do: avoid `using Plots` (no display), avoid `@show` (use `println` + `show`)
- How to handle large outputs: print shape + head/tail, save full data to CSV

#### 4c. `julia_error_handling` — Iteration and debugging guide
No parameters (static guidance).

Covers:
- How to read Julia error messages: MethodError, LoadError, UndefVarError, ArgumentError
- Common PowerAnalytics pitfalls:
  - Wrong component type name → check `poweranalytics://component-types`
  - Metric returns empty DataFrame → component has no results (check `list_result_files`)
  - `KeyError` on scenario name → list available keys first
- Iteration strategy: fix ONE error at a time, re-run, don't rewrite from scratch
- When to give up and ask the user for clarification
- Maximum retry count: 3 attempts before reporting the issue

#### 4d. `output_saving_conventions` — Where and how to save results
Parameters: `results_dir` (default: configurable)

Covers:
- Directory structure: `{results_dir}/results/` for analysis outputs
- File naming convention: `{scenario}_{component_type}_{metric}.csv`
  - Example: `Scenario_1_ThermalStandard_active_power.csv`
- When to save: always save to CSV if the DataFrame has > 10 rows
- When to just print: small summaries (< 10 rows), scalar values
- Metadata: always print the file path after saving so the user can find it
- Overwrite policy: overwrite existing files (analyses are reproducible)

#### 4e. `results_presentation` — How to present analysis to users
No parameters (static guidance).

Covers:
- Always include units: MW, MWh, $/MWh, GWh, %, hours
- Structure: start with a one-sentence summary, then details
- Numeric precision: 1-2 decimal places for MW/MWh, 0 for $ totals, 1 for %
- Comparisons: use absolute AND percentage changes ("reduced by 250 MW, a 12% decrease")
- Power systems context: explain WHY patterns occur (baseload vs peaking, merit order, curtailment causes)
- Highlight anomalies: generators at 0 MW, unexpected cost spikes, curtailment > 5%
- Multi-scenario: always compare side-by-side, note which scenario performs better and why
- Tables: use markdown tables for multi-component summaries
- Do NOT dump raw DataFrames — summarize, then point to saved CSV for full data

### Phase 5: Update tests
**File: `tests/test_poweranalytics_tools.py`**

- **Remove**: `test_get_active_power_timeseries_*` (2 tests), `test_analyze_generation_prompt`, `test_compare_scenarios_prompt` (2 tests), `test_api_reference_resource`, `test_component_types_resource` (2 tests) — 6 tests removed
- **Add**:
  - `test_get_docstring_success` — mock Julia returning docstring
  - `test_get_docstring_invalid_symbol` — injection attempt rejected
  - `test_get_docstring_invalid_module` — unknown module rejected
  - `test_get_docstring_not_found` — symbol not in module
  - `test_api_cache_initialization` — mock Julia, verify cache populated
  - `test_api_cache_fallback_on_failure` — Julia fails, fallback used
  - `test_refresh_api_index` — cache refreshed, returns count
  - `test_analyze_simulation_prompt` — master prompt contains workflow steps and references sub-prompts
  - `test_julia_coding_guide_prompt` — contains preamble, DataFrame conventions
  - `test_julia_error_handling_prompt` — contains retry strategy, common errors
  - `test_output_saving_conventions_prompt` — contains naming convention, directory structure
  - `test_results_presentation_prompt` — contains units, summarization rules
  - `test_api_index_resource` — new resource returns cached content
  - `test_component_types_resource` — new resource returns cached content
- Final count: ~23 tests (was 15, minus 6, plus 14)

### Phase 6: Update documentation
**Files: `README.md`, `SETUP.md`, `DEMO.md`**

- Update tools/resources/prompts tables
- Remove references to `get_active_power_timeseries`
- Add `get_docstring` and `refresh_api_index` to tools table
- Note that resources are now auto-generated
- Update example interactions in DEMO.md to show the new workflow

---

## Final Inventory

**Tools (5):**
| Tool | Status |
|------|--------|
| `check_julia_environment` | Kept |
| `run_julia_script` | Kept |
| `list_result_files` | Kept |
| `get_docstring` | **New** |
| `refresh_api_index` | **New** |

**Resources (2):**
| URI | Status |
|-----|--------|
| `poweranalytics://api-index` | **Replaced** (auto-generated) |
| `poweranalytics://component-types` | **Replaced** (auto-generated) |

**Prompts (5):**
| Prompt | Status | Purpose |
|--------|--------|---------|
| `analyze_simulation` | **New** (replaces 2 old prompts) | Master orchestration — the 7-step workflow |
| `julia_coding_guide` | **New** | Julia script structure, imports, DataFrame conventions, pitfalls |
| `julia_error_handling` | **New** | How to read errors, common pitfalls, retry strategy |
| `output_saving_conventions` | **New** | File naming, directory structure, when to save vs print |
| `results_presentation` | **New** | Units, precision, power systems context, summarization rules |

## Verification Plan

1. **Unit tests**: Run `.venv/bin/pytest tests/ -v` — all ~19 tests pass
2. **Manual smoke test from Claude Code**:
   - `/mcp` to reload server, verify poweranalytics appears with 5 tools
   - Call `check_julia_environment` — should pass
   - Read `poweranalytics://api-index` resource — should show auto-generated symbol list
   - Call `get_docstring("calc_active_power", "PowerAnalytics.Metrics")` — should return full docstring
   - Ask "Get thermal generation for the RTS system" — LLM should follow the 7-step workflow autonomously
3. **Fallback test**: Delete `resources/api_index.md`, restart server — resource should fall back to hardcoded text and log a warning
4. **Index generation**: Run `python generate_index.py` — verify `resources/api_index.md` and `resources/component_types.md` are created with real content

---

## Appendix: Technical Reference for Implementation

### A. Current file to modify: `server.py`
Location: `/Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics/server.py`

Key existing code to reuse:
- `_run_julia(script, project_path)` — async Julia subprocess runner (line 68). Reuse for `get_docstring` and `refresh_api_index`.
- `_format_result(result)` — formats Julia output (line 114). Reuse for error messages.
- `JULIA_PREAMBLE` — standard imports string (line 55). Include in `julia_coding_guide` prompt.
- `JULIA_EXECUTABLE`, `PA_PROJECT_PATH`, `SYSIMAGE_PATH` — config constants (lines 11-19). Reuse in `generate_index.py`.

Code to DELETE:
- `get_active_power_timeseries` function (lines 166-235)
- `get_api_reference` resource (lines 269-314)
- `get_component_types` resource (lines 317-342)
- `analyze_generation` prompt (lines 350-381)
- `compare_scenarios` prompt (lines 384-431)

### B. Julia script for API index generation

```julia
using PowerSystems
using PowerSimulations
using StorageSystemsSimulations
using HydroPowerSimulations
using DataFrames
using Dates
using CSV
using PowerAnalytics
using PowerAnalytics.Metrics

modules = [
    ("PowerAnalytics", PowerAnalytics),
    ("PowerAnalytics.Metrics", PowerAnalytics.Metrics),
]

# Check if Selectors submodule exists
if isdefined(PowerAnalytics, :Selectors)
    push!(modules, ("PowerAnalytics.Selectors", PowerAnalytics.Selectors))
end

for (mod_name, mod) in modules
    println("## $mod_name")
    println()
    for name in sort(names(mod; all=false))
        name == Symbol(mod_name) && continue
        name == Symbol(split(mod_name, ".")[end]) && continue
        obj = getfield(mod, name)
        doc_str = string(Base.doc(obj))
        # Extract first meaningful line
        lines = filter(!isempty, split(doc_str, "\n"))
        first_line = isempty(lines) ? "No documentation" : strip(lines[1])
        # Truncate long lines
        if length(first_line) > 120
            first_line = first_line[1:117] * "..."
        end
        kind = if obj isa Type
            "Type"
        elseif obj isa Function
            "Function"
        else
            "Const"
        end
        println("- `$name` [$kind]: $first_line")
    end
    println()
end
```

### C. Julia script for component types generation

```julia
using PowerSystems
using InteractiveUtils

println("# PowerSystems.jl Component Types")
println()
println("Concrete component types available for use with `make_selector()`:")
println()

abstract_types = [
    ("Generators", Generator),
    ("Storage", Storage),
    ("Electric Loads", ElectricLoad),
    ("Branches", Branch),
]

for (label, abstract_type) in abstract_types
    println("## $label")
    concrete_types = []
    for T in subtypes(abstract_type)
        if isconcretetype(T)
            push!(concrete_types, nameof(T))
        end
        for CT in subtypes(T)
            if isconcretetype(CT)
                push!(concrete_types, nameof(CT))
            end
            for CCT in subtypes(CT)
                if isconcretetype(CCT)
                    push!(concrete_types, nameof(CCT))
                end
            end
        end
    end
    for name in sort(concrete_types)
        println("- `$name`")
    end
    println()
end
```

### D. Julia script for `get_docstring` tool

Template (with `{module_name}` and `{symbol_name}` substituted by Python):

```julia
using PowerSystems
using PowerSimulations
using StorageSystemsSimulations
using HydroPowerSimulations
using DataFrames
using Dates
using CSV
using PowerAnalytics
using PowerAnalytics.Metrics

mod = {module_name}
sym = Symbol("{symbol_name}")
if isdefined(mod, sym)
    obj = getfield(mod, sym)
    println(Base.doc(obj))
else
    println("Symbol '{symbol_name}' not found in {module_name}")
end
```

### E. `generate_index.py` structure

```python
#!/usr/bin/env python3
"""Generate API index files from locally installed PowerAnalytics.jl.

Run this once after installing or updating PowerAnalytics.jl:
    python generate_index.py

Output:
    resources/api_index.md
    resources/component_types.md
"""
import asyncio, os, tempfile, subprocess
from pathlib import Path

# Reuse same config as server.py
JULIA_EXECUTABLE = os.environ.get("JULIA_EXECUTABLE", "julia")
PA_PROJECT_PATH = os.environ.get("PA_PROJECT_PATH", ".")
PA_SYSIMAGE_PATH = os.environ.get("PA_SYSIMAGE_PATH", "")
RESOURCES_DIR = Path(__file__).parent / "resources"

API_INDEX_SCRIPT = """..."""  # Julia script from Appendix B
COMPONENT_TYPES_SCRIPT = """..."""  # Julia script from Appendix C

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=PA_PROJECT_PATH)
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
```

### F. PowerAnalytics.jl installed location
`~/.julia/packages/PowerAnalytics/ALCka/`
- 9 source files, 2663 lines
- 39 exported symbols, 25 metrics, 8 selectors, 6 types
- 146+ docstrings using DocStringExtensions (TYPEDSIGNATURES template)
- Submodules: `PowerAnalytics.Metrics`, `PowerAnalytics.Selectors`

### G. Existing test file to modify
Location: `/Users/pbotin/Documents/GPAC/SIENNA_AI/SIENNA-PA-MCP/mcp_servers/poweranalytics/tests/test_poweranalytics_tools.py`
- Currently 15 async tests using pytest + pytest-asyncio
- Uses monkeypatch to mock `_run_julia` and environment variables
- Has `set_project_path` fixture that patches `PA_PROJECT_PATH` and `RESULTS_DIR`

### H. Configuration files
- `.mcp.json` (project root) — Claude Code config, already has poweranalytics server
- `.vscode/mcp.json` — VS Code chat config, already has poweranalytics server
- `pyproject.toml` — Python deps: `mcp[cli]>=1.26.0`, `pytest>=7.0.0`, `pytest-asyncio>=0.21.0`
