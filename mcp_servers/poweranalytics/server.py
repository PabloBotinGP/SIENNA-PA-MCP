import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — adjust these to match the local environment
# ---------------------------------------------------------------------------
JULIA_EXECUTABLE = os.environ.get("JULIA_EXECUTABLE", "julia")
PA_PROJECT_PATH = Path(
    os.environ.get("PA_PROJECT_PATH", ".")
)  # Julia project with PowerAnalytics.jl
RESULTS_DIR = Path(
    os.environ.get("PA_RESULTS_DIR", ".")
)  # default directory for simulation results
SCRIPT_TIMEOUT = int(os.environ.get("PA_SCRIPT_TIMEOUT", "300"))  # seconds
SYSIMAGE_PATH = os.environ.get("PA_SYSIMAGE_PATH", "")  # optional precompiled sysimage

# ---------------------------------------------------------------------------
# Resources directory and fallbacks
# ---------------------------------------------------------------------------
_RESOURCES_DIR = Path(__file__).parent / "resources"

_FALLBACK_API_INDEX = """\
# PowerAnalytics.jl — API Index

> **Note:** This is a static fallback. Run `python generate_index.py` to generate
> the full auto-generated index from your installed PowerAnalytics.jl.

## PowerAnalytics
- `create_problem_results_dict` [Function]: Load simulation results into a dictionary
- `make_selector` [Function]: Create a ComponentSelector for a PowerSystems.jl type
- `ComponentSelector` [Type]: Selector for filtering components

## PowerAnalytics.Metrics
- `calc_active_power` [Function]: Compute active power time series
- `calc_production_cost` [Function]: Compute production cost time series
- `calc_capacity_factor` [Function]: Compute capacity factor
"""

_FALLBACK_COMPONENT_TYPES = """\
# PowerSystems.jl Component Types

> **Note:** This is a static fallback. Run `python generate_index.py` to generate
> the full auto-generated list from your installed PowerSystems.jl.

## Generators
- `ThermalStandard`
- `RenewableDispatch`
- `RenewableNonDispatch`
- `HydroDispatch`
- `HydroEnergyReservoir`

## Storage
- `EnergyReservoirStorage`

## Electric Loads
- `PowerLoad`

## Branches
- `Line`
- `TapTransformer`
"""


def _load_resource(filename: str, fallback: str) -> str:
    """Load a resource file from disk, falling back to hardcoded text."""
    path = _RESOURCES_DIR / filename
    if path.is_file():
        return path.read_text()
    logger.warning(
        "Resource file %s not found. Using fallback. "
        "Run 'python generate_index.py' to generate.",
        path,
    )
    return fallback


# ---------------------------------------------------------------------------
# Julia scripts for index generation (shared with generate_index.py)
# ---------------------------------------------------------------------------

API_INDEX_SCRIPT = """\
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
    println("## ", mod_name)
    println()
    for name in sort(names(mod; all=false))
        name == Symbol(mod_name) && continue
        name == Symbol(split(mod_name, ".")[end]) && continue
        obj = getfield(mod, name)
        doc_str = string(Base.doc(obj))
        # Extract first meaningful line
        lines = filter(!isempty, split(doc_str, "\\n"))
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
        println("- `", name, "` [", kind, "]: ", first_line)
    end
    println()
end
"""

COMPONENT_TYPES_SCRIPT = """\
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
    println("## ", label)
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
        println("- `", name, "`")
    end
    println()
end
"""

# ---------------------------------------------------------------------------
# Lifespan: auto-generate resource files on first startup if missing
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server):
    """Auto-generate API index files on first startup when they are missing.

    Only runs Julia if a sysimage is configured (fast path ~5-6s).
    Falls back gracefully if Julia is unavailable or fails.
    """
    api_path = _RESOURCES_DIR / "api_index.md"
    comp_path = _RESOURCES_DIR / "component_types.md"

    if not (api_path.is_file() and comp_path.is_file()):
        sysimage = SYSIMAGE_PATH
        if sysimage and Path(sysimage).is_file():
            logger.info("API index files missing — auto-generating with sysimage...")
            _RESOURCES_DIR.mkdir(exist_ok=True)
            result = await _run_julia(API_INDEX_SCRIPT)
            if result["exit_code"] == 0:
                api_path.write_text(result["stdout"])
                symbol_count = result["stdout"].count("\n- ")
                logger.info("api_index.md generated (%d symbols).", symbol_count)
            else:
                logger.warning(
                    "API index generation failed: %s", result["stderr"][:200]
                )
            result = await _run_julia(COMPONENT_TYPES_SCRIPT)
            if result["exit_code"] == 0:
                comp_path.write_text(result["stdout"])
                logger.info("component_types.md generated.")
            else:
                logger.warning(
                    "Component types generation failed: %s", result["stderr"][:200]
                )
        else:
            logger.warning(
                "API index files missing and no sysimage configured. "
                "Run 'python generate_index.py' for the full API index."
            )
    yield


# ---------------------------------------------------------------------------
# Initialize FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "poweranalytics",
    lifespan=_lifespan,
    instructions="""
    You are a helpful assistant for analyzing power system simulation results using
    PowerAnalytics.jl — a Julia package that operates on results generated by
    PowerSimulations.jl with data structures from PowerSystems.jl.

    PowerAnalytics runs locally via the Julia REPL. There are no remote API calls.

    Workflow:
    1. Use check_julia_environment to verify the setup is correct.
    2. Read the poweranalytics://api-index resource to discover available functions.
    3. Read the poweranalytics://component-types resource to discover component types.
    4. Use get_docstring to pull full documentation for specific functions.
    5. Use run_julia_script to execute Julia code you compose from the docs.
    6. Use list_result_files to discover available simulation results and output files.

    Read the analyze_simulation prompt for the complete 7-step workflow.
    Read julia_coding_guide before writing Julia scripts.
    Read julia_error_handling when a script fails.
    Read output_saving_conventions before saving results.
    Read results_presentation before presenting analysis to the user.

    If a script fails, read the error message, fix the script, and retry (max 3 attempts).
    """,
)

# ---------------------------------------------------------------------------
# Julia execution helper
# ---------------------------------------------------------------------------

JULIA_PREAMBLE = """\
using PowerSystems
using PowerSimulations
using StorageSystemsSimulations
using HydroPowerSimulations
using DataFrames
using Dates
using CSV
using PowerAnalytics
using PowerAnalytics.Metrics
"""


async def _run_julia(script: str, project_path: str | None = None) -> dict:
    """Write *script* to a temp file, run it with Julia, return stdout + stderr.

    The subprocess ``cwd`` is set to *project_path* so that relative paths
    inside Julia scripts (e.g. ``_simulation_results_RTS``) resolve correctly.
    """
    project = project_path or str(PA_PROJECT_PATH)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jl", delete=False
    ) as tmp:
        tmp.write(script)
        tmp_path = tmp.name

    try:
        cmd = [JULIA_EXECUTABLE]
        # Use precompiled sysimage if available (Phase 1 optimisation)
        sysimage = SYSIMAGE_PATH
        if sysimage and Path(sysimage).is_file():
            cmd += [f"--sysimage={sysimage}"]
        cmd += [f"--project={project}", tmp_path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project,  # run from project root so relative paths work
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SCRIPT_TIMEOUT
        )
        return {
            "exit_code": proc.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Script timed out after {SCRIPT_TIMEOUT} seconds.",
        }
    finally:
        os.unlink(tmp_path)


def _format_result(result: dict) -> str:
    """Format a Julia execution result into a readable string."""
    parts = []
    if result["exit_code"] != 0:
        parts.append(f"Exit code: {result['exit_code']}")
    if result["stderr"]:
        parts.append(f"--- stderr ---\n{result['stderr']}")
    if result["stdout"]:
        parts.append(f"--- stdout ---\n{result['stdout']}")
    if not result["stdout"] and not result["stderr"]:
        parts.append("(no output)")
    return "\n".join(parts)


# ===================================================================
# TOOLS
# ===================================================================


@mcp.tool()
async def run_julia_script(script: str, project_path: str | None = None) -> str:
    """Execute an arbitrary Julia script and return its output.

    The script runs as a subprocess with the PowerAnalytics.jl project activated.
    Use this for custom analysis not covered by the high-level tools.

    Args:
        script: Complete Julia source code to execute.
        project_path: Optional path to a Julia project to activate (defaults to PA_PROJECT_PATH).
    """
    result = await _run_julia(script, project_path)
    return _format_result(result)


@mcp.tool()
async def check_julia_environment(project_path: str | None = None) -> str:
    """Verify that Julia is available and PowerAnalytics.jl can be loaded.

    Args:
        project_path: Optional path to the Julia project to check.
    """
    script = f"""{JULIA_PREAMBLE}
println("Julia version: ", VERSION)
println("PowerAnalytics loaded successfully.")
println("Project: ", Base.active_project())
"""
    result = await _run_julia(script, project_path)
    if result["exit_code"] == 0:
        return f"Environment OK.\n{result['stdout']}"
    return f"Environment check FAILED.\n{_format_result(result)}"


@mcp.tool()
async def get_docstring(
    symbol_name: str, module_name: str = "PowerAnalytics"
) -> str:
    """Get the full Julia docstring for a specific symbol.

    Use this to read detailed documentation (signature, arguments, return type,
    examples) for functions discovered in the poweranalytics://api-index resource.

    Args:
        symbol_name: Name of the Julia symbol (e.g. "calc_active_power", "make_selector").
        module_name: Module containing the symbol. One of: "PowerAnalytics",
            "PowerAnalytics.Metrics", "PowerAnalytics.Selectors".
    """
    # Input validation
    if not symbol_name.isidentifier():
        return f"Error: Invalid symbol name '{symbol_name}'. Must be a valid Julia identifier."

    allowed_modules = {
        "PowerAnalytics",
        "PowerAnalytics.Metrics",
        "PowerAnalytics.Selectors",
    }
    if module_name not in allowed_modules:
        return (
            f"Error: Unknown module '{module_name}'. "
            f"Allowed modules: {', '.join(sorted(allowed_modules))}"
        )

    script = f"""{JULIA_PREAMBLE}
mod = {module_name}
sym = Symbol("{symbol_name}")
if isdefined(mod, sym)
    obj = getfield(mod, sym)
    println(Base.doc(obj))
else
    println("Symbol '{symbol_name}' not found in {module_name}")
end
"""
    result = await _run_julia(script)
    if result["exit_code"] == 0:
        return result["stdout"].strip()
    return f"Error retrieving docstring:\n{_format_result(result)}"


@mcp.tool()
async def refresh_api_index() -> str:
    """Regenerate the API index and component types from the installed Julia packages.

    Runs the same Julia scripts as generate_index.py, overwrites the
    resources/*.md files, and returns the updated symbol count.
    Use this after updating PowerAnalytics.jl without restarting the server.
    """
    _RESOURCES_DIR.mkdir(exist_ok=True)
    errors = []

    # Generate API index
    result = await _run_julia(API_INDEX_SCRIPT)
    if result["exit_code"] == 0:
        (_RESOURCES_DIR / "api_index.md").write_text(result["stdout"])
    else:
        errors.append(f"API index generation failed:\n{_format_result(result)}")

    # Generate component types
    result = await _run_julia(COMPONENT_TYPES_SCRIPT)
    if result["exit_code"] == 0:
        (_RESOURCES_DIR / "component_types.md").write_text(result["stdout"])
    else:
        errors.append(f"Component types generation failed:\n{_format_result(result)}")

    if errors:
        return "Partial failure:\n" + "\n".join(errors)

    api_text = (_RESOURCES_DIR / "api_index.md").read_text()
    symbol_count = api_text.count("\n- ")
    return f"API index refreshed. {symbol_count} symbols indexed."


@mcp.tool()
async def list_result_files(directory: str | None = None, pattern: str = "*") -> str:
    """List files in a directory, useful for discovering simulation results or saved outputs.

    Args:
        directory: Path to search. Defaults to the configured results directory.
        pattern: Glob pattern to filter files (e.g. "*.csv", "*.h5").
    """
    search_dir = Path(directory) if directory else RESULTS_DIR
    if not search_dir.exists():
        return f"Directory not found: {search_dir}"

    files = sorted(search_dir.rglob(pattern))
    if not files:
        return f"No files matching '{pattern}' in {search_dir}"

    lines = [f"Files in {search_dir} (pattern: {pattern}):"]
    for f in files[:100]:  # cap at 100 entries
        rel = f.relative_to(search_dir)
        size_kb = f.stat().st_size / 1024
        lines.append(f"  {rel}  ({size_kb:.1f} KB)")
    if len(files) > 100:
        lines.append(f"  ... and {len(files) - 100} more files")
    return "\n".join(lines)


# ===================================================================
# RESOURCES
# ===================================================================


@mcp.resource("poweranalytics://api-index")
def get_api_index() -> str:
    """Auto-generated one-line-per-symbol index of all PowerAnalytics.jl exports."""
    return _load_resource("api_index.md", _FALLBACK_API_INDEX)


@mcp.resource("poweranalytics://component-types")
def get_component_types() -> str:
    """Auto-generated PowerSystems.jl component type hierarchy."""
    return _load_resource("component_types.md", _FALLBACK_COMPONENT_TYPES)


# ===================================================================
# PROMPTS
# ===================================================================


@mcp.prompt()
def analyze_simulation(
    task_description: str = "Analyze the simulation results",
    results_dir: str = "_simulation_results_RTS",
    problem_name: str = "UC",
) -> str:
    """Master orchestration prompt — the 7-step workflow for any analysis task.

    This is the entry point for every analysis request. It teaches the complete
    workflow: discover API, read docs, write Julia scripts, execute, save, present.

    Args:
        task_description: What the user wants to analyze.
        results_dir: Path to the directory containing simulation results.
        problem_name: Name of the decision model (e.g. "UC").
    """
    return f"""\
## Task
{task_description}

## Simulation Context
- Results directory: `{results_dir}`
- Problem name: `{problem_name}`

## 7-Step Workflow

Follow these steps in order:

### Step 1: Check Environment
Call `check_julia_environment()` to verify Julia and PowerAnalytics.jl are available.

### Step 2: Read API Index
Read the `poweranalytics://api-index` resource to discover available functions, types,
and constants. Scan the index and identify which symbols are relevant to the task.

### Step 3: Read Component Types
Read the `poweranalytics://component-types` resource to identify which PowerSystems.jl
component types are relevant (e.g. ThermalStandard, RenewableDispatch).

### Step 4: Get Docstrings
For each relevant function identified in Step 2, call `get_docstring(symbol_name, module_name)`
to read the full signature, argument descriptions, and usage examples.
Typically you need 1-3 docstrings per task.

### Step 5: Write and Execute Julia Script
Compose a Julia script based on the docstrings. Read the `julia_coding_guide` prompt
for best practices on script structure and imports.

Execute with `run_julia_script(script)`.

If the script fails, read the `julia_error_handling` prompt, fix the issue, and retry
(max 3 attempts).

### Step 6: Save Results
Follow the `output_saving_conventions` prompt for file naming and directory structure.
Save DataFrames with > 10 rows to CSV. Print the saved file path.

### Step 7: Analyze and Present
Follow the `results_presentation` prompt. Summarize results with units (MW, MWh, $/MWh).
Explain patterns in power systems context. Point to saved CSVs for full data.

## Worked Example: Thermal Generation Analysis

Task: "Get thermal generation for the RTS system"

1. `check_julia_environment()` → OK
2. Read `poweranalytics://api-index` → find `create_problem_results_dict`, `make_selector`, `calc_active_power`
3. Read `poweranalytics://component-types` → identify `ThermalStandard`
4. `get_docstring("calc_active_power", "PowerAnalytics.Metrics")` → full signature
   `get_docstring("make_selector", "PowerAnalytics")` → selector docs
5. Write and execute:
```julia
{JULIA_PREAMBLE}
results_all = create_problem_results_dict("{results_dir}", "{problem_name}"; populate_system = true)
results_uc = results_all[first(keys(results_all))]
selector = make_selector(ThermalStandard)
df = calc_active_power(selector, results_uc)
println("Shape: ", size(df))
println("Columns: ", names(df))
println()
println("First rows:")
show(stdout, "text/plain", first(df, 5))
println()
CSV.write("results/Scenario_1_ThermalStandard_active_power.csv", df)
println("Saved to results/Scenario_1_ThermalStandard_active_power.csv")
```
6. File saved to `results/Scenario_1_ThermalStandard_active_power.csv`
7. Present: "76 thermal units, 744 hourly periods. Nuclear baseload at ~400 MW,
   combined-cycle units range 170-355 MW, peaking CTs dispatched during high-demand hours."
"""


@mcp.prompt()
def julia_coding_guide() -> str:
    """Julia code generation best practices for PowerAnalytics.jl scripts.

    Covers required imports, script structure, DataFrame conventions, type system,
    common patterns, and what to avoid.
    """
    return f"""\
## Julia Coding Guide for PowerAnalytics.jl

### Required Imports (always include this preamble)
```julia
{JULIA_PREAMBLE}```

### Script Structure
Every analysis script follows this pattern:
1. **Imports** (the preamble above)
2. **Load results**: `create_problem_results_dict(results_dir, problem_name; populate_system=true)`
3. **Select scenario**: `results_uc = results_all[first(keys(results_all))]`
4. **Create selectors**: `selector = make_selector(ComponentType)`
5. **Compute metrics**: `df = calc_some_metric(selector, results_uc)`
6. **Output results**: print summary, save to CSV if large

### DataFrame Conventions
- First column is always `DateTime` (hourly timestamps)
- Data columns are named `TypeName__component_name` (e.g. `ThermalStandard__321_CC_1`)
- Access data columns: `names(df)[2:end]` (skip DateTime)
- Total across components: `sum(eachcol(df[!, names(df)[2:end]]))`

### Type System
- **Concrete types** for selectors: `ThermalStandard`, `RenewableDispatch`, `EnergyReservoirStorage`
- **Abstract types** for broader queries: `ThermalGen`, `RenewableGen`, `Storage`
- When in doubt, check `poweranalytics://component-types` resource
- Always use the concrete type with `make_selector()` unless you want all subtypes

### Common Patterns

**Iterate over scenarios:**
```julia
for (name, results_uc) in results_all
    df = calc_active_power(selector, results_uc)
    println("Scenario: ", name, " — Shape: ", size(df))
end
```

**Aggregate across time:**
```julia
gen_cols = names(df)[2:end]
avg_per_unit = [mean(df[!, col]) for col in gen_cols]
```

**Filter to specific components:**
```julia
# Use make_selector with specific component names
selector = make_selector(ThermalStandard, "321_CC_1")
```

### What NOT to Do
- Do NOT use `using Plots` or any plotting library (no display available)
- Do NOT use `@show` — use `println()` and `show(stdout, "text/plain", df)`
- Do NOT print entire large DataFrames — print `size(df)`, `first(df, 5)`, `last(df, 5)`
- Do NOT hardcode paths — use the `results_dir` parameter

### Handling Large Outputs
If a DataFrame has many rows:
```julia
println("Shape: ", size(df))
println("Columns: ", names(df))
println("\\nFirst 5 rows:")
show(stdout, "text/plain", first(df, 5))
println("\\n\\nLast 5 rows:")
show(stdout, "text/plain", last(df, 5))
CSV.write("results/output.csv", df)
println("\\nFull data saved to results/output.csv")
```
"""


@mcp.prompt()
def julia_error_handling() -> str:
    """Guide for iterating and debugging Julia script errors.

    Covers how to read Julia error messages, common PowerAnalytics pitfalls,
    iteration strategy, and when to give up.
    """
    return """\
## Julia Error Handling Guide

### Reading Julia Error Messages

**MethodError: no method matching func(::Type1, ::Type2)**
- You passed wrong argument types. Check the docstring for correct signature.
- Common cause: passing a string where a Type is expected (e.g. "ThermalStandard" instead of ThermalStandard).

**LoadError: UndefVarError: `name` not defined**
- Missing import. Add the appropriate `using` statement.
- Check if the symbol exists in the module: read the API index resource.

**ArgumentError: ...**
- Wrong argument value. Read the full error message for expected values.
- Common cause: wrong problem_name or results_dir path.

**KeyError: key "Scenario_X" not found**
- The scenario name doesn't exist. List available keys first:
  `println(keys(results_all))`

### Common PowerAnalytics Pitfalls

1. **Wrong component type name**: Use exact names from `poweranalytics://component-types`.
   Wrong: `Thermal`, `ThermalGenerator` — Right: `ThermalStandard`

2. **Metric returns empty DataFrame**: The component type has no results in this simulation.
   Check with `list_result_files` that the simulation ran successfully.

3. **Path not found**: Relative paths resolve from `PA_PROJECT_PATH`. Use absolute paths if unsure.

4. **Out of memory**: Large multi-scenario analyses can be memory-intensive.
   Process one scenario at a time instead of loading all at once.

### Iteration Strategy
1. Read the FULL error message carefully
2. Fix ONE error at a time
3. Re-run the script
4. Do NOT rewrite the entire script from scratch — modify the failing part
5. Maximum 3 retry attempts before reporting the issue to the user

### When to Ask the User
- After 3 failed attempts with different errors
- When the error suggests missing data or configuration issues
- When the requested analysis is ambiguous
"""


@mcp.prompt()
def output_saving_conventions(results_dir: str = "_simulation_results_RTS") -> str:
    """Conventions for where and how to save analysis results.

    Args:
        results_dir: Base directory for simulation results (used to derive output path).
    """
    return f"""\
## Output Saving Conventions

### Directory Structure
Save analysis outputs to: `{results_dir}/results/`

Create the directory in your Julia script if it doesn't exist:
```julia
mkpath("{results_dir}/results")
```

### File Naming Convention
`{{scenario}}_{{ComponentType}}_{{metric}}.csv`

Examples:
- `Scenario_1_ThermalStandard_active_power.csv`
- `Scenario_2_RenewableDispatch_capacity_factor.csv`
- `all_scenarios_EnergyReservoirStorage_energy.csv`

### When to Save
- **Always save** if the DataFrame has > 10 rows → CSV file
- **Just print** for small summaries (< 10 rows), scalar values, or aggregated statistics

### When to Just Print
- Single numeric results: "Total cost: $1,234,567"
- Small summary tables: capacity factors per generator (< 10 rows)
- Comparison summaries: scenario A vs B key metrics

### After Saving
Always print the file path so the user can find it:
```julia
CSV.write("path/to/file.csv", df)
println("Results saved to path/to/file.csv")
```

### Overwrite Policy
Overwrite existing files — analyses are reproducible from simulation data.
"""


@mcp.prompt()
def results_presentation() -> str:
    """Guide for presenting analysis results to the user.

    Covers units, precision, structure, comparisons, and power systems context.
    """
    return """\
## Results Presentation Guide

### Always Include Units
- Power: MW (megawatts)
- Energy: MWh or GWh (megawatt-hours, gigawatt-hours)
- Cost: $/MWh or total $
- Percentage: %
- Time: hours

### Structure
1. **One-sentence summary** of the key finding
2. **Details** with specific numbers
3. **Context** explaining why the pattern occurs
4. **Saved files** pointing to CSVs for full data

### Numeric Precision
- MW / MWh: 1-2 decimal places (e.g. 245.3 MW)
- Dollar totals: 0 decimal places (e.g. $1,234,567)
- Percentages: 1 decimal place (e.g. 12.3%)
- Capacity factors: 1 decimal place (e.g. 34.7%)

### Comparisons
Use BOTH absolute and percentage changes:
- "Reduced by 250 MW, a 12% decrease"
- "Cost increased from $2.1M to $2.4M (+14%)"

### Power Systems Context
Explain WHY patterns occur:
- Baseload units (nuclear, large coal) run constantly at high output
- Peaking units (CTs, gas turbines) only dispatch during high-demand periods
- Renewables have variable output driven by weather (wind speed, solar irradiance)
- Storage charges during low-price hours and discharges during high-price hours
- Curtailment occurs when renewable generation exceeds demand minus must-run generation

### Highlight Anomalies
Flag these if they appear:
- Generators at 0 MW for the entire period (may indicate outage or decommitment)
- Unexpected cost spikes (may indicate scarcity pricing)
- Curtailment > 5% (may indicate transmission constraints or oversupply)
- Storage cycling patterns that don't match expected arbitrage behavior

### Multi-Scenario Comparisons
- Always compare side-by-side in a markdown table
- Note which scenario performs better and why
- Quantify the difference in absolute and percentage terms

### Do NOT
- Dump raw DataFrames — summarize, then point to saved CSV
- Use technical jargon without explanation
- Present numbers without units
- Ignore anomalies or unexpected patterns
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
