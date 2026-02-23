import asyncio
import logging
import os
import tempfile
import textwrap
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
JULIA_HEAP_SIZE = os.environ.get("JULIA_MCP_MEMORY_LIMIT", "")  # e.g. "4G" → --heap-size-hint

# ---------------------------------------------------------------------------
# Resources directory and fallbacks
# ---------------------------------------------------------------------------
_RESOURCES_DIR = Path(__file__).parent / "resources"

_FALLBACK_API_INDEX = """\
# PowerAnalytics.jl — API Index

> **Note:** This is a static fallback approximation. Run `python generate_index.py` or
> call `refresh_api_index()` to generate the full auto-generated index from your
> installed PowerAnalytics.jl. Some functions listed here may not exist in your version.

## PowerSimulations (Recommended primary path — no system JSON needed)

Use these for reliable data access. They work without `set_system!` or a system JSON file.

- `PowerSimulations.SimulationResults(path)` [Function]: Load simulation results from directory
- `PowerSimulations.get_decision_problem_results(sr, problem_name)` [Function]: Get results for a specific decision problem
- `read_variable(pr, VariableType, ComponentType)` [Function]: Read a single variable
  - Signature: `read_variable(pr, ActivePowerVariable, ThermalStandard)`
  - **Returns:** `SortedDict{DateTime, DataFrame}` — one entry per execution step (NOT a single DataFrame)
  - Each sub-DataFrame has 3 columns: `DateTime`, `name` (component name), `value` (MW) — **long/tidy format**
  - Optional kwargs: `initial_time::DateTime`, `count::Int` (number of timesteps, NOT end time)
  - **Note:** use `count`, not a stop time. Example: `count=7*24` for one week of hourly data.
  - **Note:** if `initial_time` falls mid-step, `count` measures from that timestamp. Align to execution step starts for predictable results.
  - Requires: `using PowerSystems` for component type, `using PowerSimulations` for variable type
- `list_variable_keys(pr)` [Function]: List all available (VariableType, ComponentType) pairs
  - Output is verbose — use the pretty-print pattern from `julia_coding_guide` to extract readable names
- `get_timestamps(pr)` [Function]: Return execution step start times (one per rolling-horizon solve)
  - **Note:** This returns the simulation execution cadence (e.g. 31 daily starts), NOT the individual data timesteps (e.g. 744 hourly values). For the full time axis, use the `DateTime` column from `read_variable`.

## PowerAnalytics (High-level path — requires system JSON via `set_system!`)

> **WARNING:** The high-level metric functions (`calc_active_power`, etc.) require a
> PowerSystems system JSON file attached to the results via `set_system!(pr, path)`.
> If your simulation results don't include a system JSON, use `read_variable` above.

- `create_problem_results_dict` [Function]: Load simulation results into a Dict mapping scenario name → ProblemResults
  - Signature: `create_problem_results_dict(results_dir, problem_name; scenarios=nothing)`
  - **Always pass `scenarios` explicitly** to avoid scanning non-simulation subdirectories.
- `make_selector` [Function]: Create a ComponentSelector for filtering by PowerSystems.jl component type
  - Signature: `make_selector(ComponentType)` or `make_selector(ComponentType, "name_substring")`
- `ComponentSelector` [Type]: Selector object used by all `calc_*` metric functions

## PowerAnalytics.Metrics (requires system JSON)

- `calc_active_power` [Const]: Compute active power time series for selected components
  - Usage: `compute(calc_active_power, results, selector)` (requires `set_system!` first)
- `calc_production_cost` [Const]: Compute production cost time series
- `calc_capacity_factor` [Const]: Compute capacity factor (generation / capacity)
- `calc_active_power_in` [Const]: Compute active power flowing into storage/loads
- `calc_active_power_out` [Const]: Compute active power flowing out of storage
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
using Logging
global_logger(ConsoleLogger(stderr, Logging.Warn))

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
        # Guard against symbols that are exported but not defined (e.g.
        # PluralComponentSelector in some PowerAnalytics versions)
        if !isdefined(mod, name)
            continue
        end
        try
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
        catch e
            # Skip symbols that can't be introspected (re-exports, broken bindings)
            @warn "Skipping symbol $name in $mod_name" exception=e
        end
    end
    println()
end
"""

COMPONENT_TYPES_SCRIPT = """\
using Logging
global_logger(ConsoleLogger(stderr, Logging.Warn))

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
    """Lightweight startup — no Julia calls to avoid blocking MCP handshake.

    Resource auto-generation is deferred to the first `check_julia_environment`
    call so that the MCP server registers tools immediately.
    """
    _RESOURCES_DIR.mkdir(exist_ok=True)
    logger.info("PowerAnalytics MCP server started (tools registered).")
    yield


_auto_gen_attempted = False  # Prevent repeated auto-generation attempts


async def _auto_generate_resources() -> str | None:
    """Auto-generate API index files if missing and sysimage is available.

    Returns a status message, or None if no generation was needed.
    Called by check_julia_environment after verifying Julia works.

    Uses a module-level flag to prevent retrying a failed generation on every
    call — once attempted (success or failure), subsequent calls return None
    until the server is restarted or refresh_api_index() is called explicitly.
    """
    global _auto_gen_attempted

    api_path = _RESOURCES_DIR / "api_index.md"
    comp_path = _RESOURCES_DIR / "component_types.md"

    if api_path.is_file() and comp_path.is_file():
        return None

    # Don't retry if we already attempted (and failed) in this server session
    if _auto_gen_attempted:
        return None

    sysimage = SYSIMAGE_PATH
    if not (sysimage and Path(sysimage).is_file()):
        return (
            "API index files missing and no sysimage configured. "
            "Run 'python generate_index.py' or call refresh_api_index() "
            "for the full API index."
        )

    _auto_gen_attempted = True
    logger.info("API index files missing — auto-generating with sysimage...")
    messages = []

    result = await _run_julia(API_INDEX_SCRIPT)
    if result["exit_code"] == 0:
        api_path.write_text(result["stdout"])
        symbol_count = result["stdout"].count("\n- ")
        messages.append(f"api_index.md generated ({symbol_count} symbols).")
    else:
        messages.append(f"API index generation failed: {result['stderr'][:200]}")

    result = await _run_julia(COMPONENT_TYPES_SCRIPT)
    if result["exit_code"] == 0:
        comp_path.write_text(result["stdout"])
        messages.append("component_types.md generated.")
    else:
        messages.append(f"Component types generation failed: {result['stderr'][:200]}")

    return "\n".join(messages)


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
# Suppress Info-level logging to prevent stderr contamination of MCP stdio stream.
# Julia's [ Info: ] messages from package loading and data operations can corrupt
# the JSON-RPC framing, causing -32000 "Connection closed" errors.
using Logging
global_logger(ConsoleLogger(stderr, Logging.Warn))

using PowerSystems
using PowerSimulations
using StorageSystemsSimulations
using HydroPowerSimulations
using DataFrames
using Dates
using CSV
using Statistics
using PowerAnalytics
using PowerAnalytics.Metrics
"""

# Maximum characters for stderr output to prevent buffer overflow and context bloat
_MAX_STDERR_LENGTH = 2000


async def _run_julia(script: str, project_path: str | None = None) -> dict:
    """Write *script* to a temp file, run it with Julia, return stdout + stderr.

    Behaviour:
    - ``cwd`` is set to *project_path* so relative paths resolve correctly.
    - A ``PROJECT_DIR`` constant is injected at the top of every script so
      scripts can reference the project root without relying on ``@__DIR__``
      (which resolves to the temp file's directory, not the project root).
    - If ``JULIA_MCP_MEMORY_LIMIT`` is set the ``--heap-size-hint`` flag is
      passed so Julia triggers a graceful ``OutOfMemoryError`` instead of
      being killed by the OS.
    - Out-of-memory conditions are detected and returned as a structured error
      message rather than a silent "Connection closed".
    - **Stderr is redirected to a temp file** (not a pipe) to prevent pipe
      buffer deadlocks that cause -32000 "Connection closed" errors. Julia
      packages can emit large volumes of stderr during loading and data
      operations that fill the OS pipe buffer (~64KB), blocking the process.
    """
    project = project_path or str(PA_PROJECT_PATH)

    # Inject PROJECT_DIR so scripts don't need to rely on @__DIR__
    preamble = f'const PROJECT_DIR = raw"{project}"\n'
    full_script = preamble + script

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jl", delete=False
    ) as tmp:
        tmp.write(full_script)
        tmp_path = tmp.name

    # Redirect stderr to a temp file to avoid pipe buffer deadlock.
    # Julia packages emit large volumes of stderr (Info logs, precompilation
    # messages, warnings) that can fill the OS pipe buffer (~64KB on most
    # systems). When both stdout and stderr are pipes, a full stderr buffer
    # blocks the Julia process, which in turn blocks stdout, causing
    # asyncio.communicate() to hang until the MCP client times out with
    # error -32000 "Connection closed".
    stderr_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_stderr.txt", delete=False
    )

    try:
        cmd = [JULIA_EXECUTABLE]
        # Graceful OOM: Julia raises OutOfMemoryError instead of being SIGKILL'd
        if JULIA_HEAP_SIZE:
            cmd += [f"--heap-size-hint={JULIA_HEAP_SIZE}"]
        # Use precompiled sysimage if available (Phase 1 optimisation)
        sysimage = SYSIMAGE_PATH
        if sysimage and Path(sysimage).is_file():
            cmd += [f"--sysimage={sysimage}"]
        cmd += [f"--project={project}", tmp_path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr_tmp,  # temp file, NOT a pipe — prevents deadlock
            cwd=project,  # run from project root so relative paths work
        )
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=SCRIPT_TIMEOUT
        )
        stdout_str = stdout_bytes.decode()

        # Read stderr from the temp file after the process completes
        stderr_tmp.close()
        stderr_str = Path(stderr_tmp.name).read_text()

        # Detect out-of-memory conditions (SIGKILL from OS or Julia OOM error)
        is_oom = (
            proc.returncode in (-9, 137)  # SIGKILL (Linux/macOS OOM killer)
            or "OutOfMemoryError" in stderr_str
            or "Cannot allocate memory" in stderr_str
            or "out of memory" in stderr_str.lower()
        )
        if is_oom:
            oom_hint = (
                "Julia process ran out of memory.\n"
                "Suggestions:\n"
                "  1. Use `read_variable` directly with `initial_time` and `count` to process smaller time windows.\n"
                "  2. Break the script into smaller steps — save intermediate results to CSV and load in the next script.\n"
                "  3. Set the JULIA_MCP_MEMORY_LIMIT env var (e.g. '4G') for a graceful OOM error next time.\n"
                "  4. Read the `julia_error_handling` prompt for the full low-memory alternative workflow.\n"
            )
            if stderr_str:
                oom_hint += f"\nOriginal stderr:\n{stderr_str}"
            return {"exit_code": proc.returncode, "stdout": stdout_str, "stderr": oom_hint}

        return {
            "exit_code": proc.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": (
                f"Script timed out after {SCRIPT_TIMEOUT} seconds "
                f"(controlled by PA_SCRIPT_TIMEOUT env var).\n"
                "For large datasets consider processing in smaller time chunks."
            ),
        }
    finally:
        os.unlink(tmp_path)
        try:
            os.unlink(stderr_tmp.name)
        except OSError:
            pass


def _format_result(result: dict) -> str:
    """Format a Julia execution result into a readable string.

    Shows stdout first (the actual data), then stderr (diagnostics).
    Filters out Julia's informational '[ Info: ]' log lines from stderr
    regardless of exit code — they add noise and are never actionable.
    Truncates stderr to ``_MAX_STDERR_LENGTH`` to prevent buffer overflow
    and excessive context consumption.
    """
    parts = []
    if result["exit_code"] != 0:
        parts.append(f"Exit code: {result['exit_code']}")
    if result["stdout"]:
        parts.append(f"--- stdout ---\n{result['stdout']}")
    # Filter Info lines always — they're noise from package loading / data ops
    stderr = result["stderr"]
    if stderr:
        stderr = "\n".join(
            line for line in stderr.splitlines()
            if not line.strip().startswith("[ Info:")
        ).strip()
    # Truncate verbose error output (e.g. MethodError dumping entire objects)
    if stderr and len(stderr) > _MAX_STDERR_LENGTH:
        stderr = stderr[:_MAX_STDERR_LENGTH] + "\n... (stderr truncated)"
    if stderr:
        parts.append(f"--- stderr ---\n{stderr}")
    if not result["stdout"] and not stderr:
        parts.append("(no output)")
    return "\n".join(parts)


# ===================================================================
# TOOLS
# ===================================================================


@mcp.tool()
async def run_julia_script(script: str, project_path: str | None = None) -> str:
    """Execute an arbitrary Julia script and return its output.

    The script runs as a subprocess with the PowerAnalytics.jl project activated.
    The standard preamble (package imports + logging suppression) is automatically
    prepended unless the script already manages its own imports (detected by the
    presence of `using PowerAnalytics`, `using PowerSimulations`, `using Logging`,
    `redirect_stderr`, or `global_logger`).

    Args:
        script: Complete Julia source code to execute.
        project_path: Optional path to a Julia project to activate (defaults to PA_PROJECT_PATH).
    """
    # Detect if the script has its own import/stderr management
    _has_own_imports = any(kw in script for kw in [
        "using PowerAnalytics",
        "using PowerSimulations",
        "using Logging",
        "redirect_stderr",
        "global_logger",
    ])

    preamble_injected = False
    if not _has_own_imports:
        script = JULIA_PREAMBLE + "\n" + script
        preamble_injected = True

    result = await _run_julia(script, project_path)
    formatted = _format_result(result)

    if preamble_injected:
        formatted = "(Note: standard preamble was auto-prepended)\n" + formatted

    return formatted


@mcp.tool()
async def check_julia_environment(project_path: str | None = None) -> str:
    """Verify that Julia is available and PowerAnalytics.jl can be loaded.

    Also auto-generates API index files on first call if they are missing
    and a sysimage is available.

    Args:
        project_path: Optional path to the Julia project to check.
    """
    script = f"""{JULIA_PREAMBLE}
println("Julia version: ", VERSION)
println("PowerAnalytics loaded successfully.")
println("Project: ", Base.active_project())
"""
    result = await _run_julia(script, project_path)
    if result["exit_code"] != 0:
        return f"Environment check FAILED.\n{_format_result(result)}"

    parts = [f"Environment OK.\n{result['stdout']}"]

    # Auto-generate resource files if missing (deferred from lifespan)
    gen_msg = await _auto_generate_resources()
    if gen_msg:
        parts.append(f"\nResource generation: {gen_msg}")

    return "\n".join(parts)


@mcp.tool()
async def get_docstring(
    symbol_name: str, module_name: str = "PowerAnalytics"
) -> str:
    """Get the full Julia docstring for a specific symbol.

    Use this to read detailed documentation (signature, arguments, return type,
    examples) for functions discovered in the poweranalytics://api-index resource.

    **IMPORTANT:** Do NOT call multiple `get_docstring` in parallel. Each call
    spawns a Julia subprocess; parallel calls can overwhelm the MCP connection.
    Call them sequentially (one at a time).

    Args:
        symbol_name: Name of the Julia symbol (e.g. "calc_active_power", "make_selector").
        module_name: Module containing the symbol. One of: "PowerAnalytics",
            "PowerAnalytics.Metrics", "PowerAnalytics.Selectors",
            "PowerSimulations", "PowerSystems", "DataFrames".
    """
    # Input validation
    if not symbol_name.isidentifier():
        return f"Error: Invalid symbol name '{symbol_name}'. Must be a valid Julia identifier."

    allowed_modules = {
        "PowerAnalytics",
        "PowerAnalytics.Metrics",
        "PowerAnalytics.Selectors",
        "PowerSimulations",
        "PowerSystems",
        "DataFrames",
    }
    if module_name not in allowed_modules:
        return (
            f"Error: Unknown module '{module_name}'. "
            f"Allowed modules: {', '.join(sorted(allowed_modules))}"
        )

    # Use @doc syntax to get the docstring attached to the *binding* (e.g.
    # `@doc PowerAnalytics.Metrics.calc_active_power`), not the docstring of
    # the object's type.  `Base.doc(getfield(mod, sym))` would return the
    # docstring for `ComponentTimedMetric` when called on an instance like
    # `calc_active_power`, which is wrong.
    script = f"""{JULIA_PREAMBLE}
mod = {module_name}
sym = Symbol("{symbol_name}")
if isdefined(mod, sym)
    obj = getfield(mod, sym)

    # Use @doc on the binding, not on the object value
    doc_str = string(eval(:(@doc $mod.$sym)))
    lines = filter(!isempty, split(doc_str, "\\n"))
    has_content = length(lines) >= 2

    # For Const values (e.g. metric instances), also show type and name info
    if !(obj isa Function) && !(obj isa Type)
        println("## `{symbol_name}` — ", typeof(obj))
        println()
    end

    if has_content
        # Truncate very long docstrings (e.g. from generic types) to 3000 chars
        if length(doc_str) > 3000
            println(doc_str[1:3000])
            println("\\n... (docstring truncated)")
        else
            println(doc_str)
        end
        println()
    end

    # Always show concrete method signatures for functions
    if obj isa Function
        ms = methods(obj)
        if length(ms) > 0
            println("## Method signatures for `{symbol_name}`")
            println()
            for m in ms
                println("  ", m)
            end
        else
            println("No methods found for `{symbol_name}` in {module_name}.")
        end
    elseif !has_content
        println("No documentation found for `{symbol_name}` in {module_name}.")
    end
else
    println("Symbol `{symbol_name}` not found in {module_name}.")
    println("Tip: check the poweranalytics://api-index resource for the correct module.")
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
    global _auto_gen_attempted
    _RESOURCES_DIR.mkdir(exist_ok=True)
    _auto_gen_attempted = True  # Mark as attempted so auto-gen doesn't re-run
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
2. Read `poweranalytics://api-index` → find `read_variable`, `list_variable_keys`
3. Read `poweranalytics://component-types` → identify `ThermalStandard`
4. `get_docstring("read_variable", "PowerSimulations")` → full signature
5. Write and execute:
```julia
{JULIA_PREAMBLE}

# Load results for one scenario — no populate_system needed (low memory)
scenario_path = joinpath("{results_dir}", "Scenario_1")
sr = PowerSimulations.SimulationResults(scenario_path)
pr = PowerSimulations.get_decision_problem_results(sr, "{problem_name}")

# Read thermal generation — returns SortedDict{{DateTime, DataFrame}}
raw = read_variable(pr, ActivePowerVariable, ThermalStandard)
println("Execution steps: ", length(raw))

# Deduplicate rolling-horizon overlap (keep realized portion only)
exec_times = sort(collect(keys(raw)))
step = exec_times[min(2, length(exec_times))] - exec_times[1]  # e.g. Day(1)
realized = DataFrame[]
for (i, t) in enumerate(exec_times)
    sub = copy(raw[t])
    t_next = i < length(exec_times) ? exec_times[i+1] : t + step
    filter!(row -> row.DateTime >= t && row.DateTime < t_next, sub)
    push!(realized, sub)
end
df_long = vcat(realized...)

# Pivot to wide format for per-generator analysis
df_wide = unstack(df_long, :DateTime, :name, :value)
sort!(df_wide, :DateTime)
gen_cols = names(df_wide)[2:end]
println("Shape: ", size(df_wide))
println("Generators: ", length(gen_cols))
println("\\nFirst rows:")
show(stdout, "text/plain", first(df_wide, 5))
println()

# Save — NEVER inside the simulation results folder
out_path = joinpath(PROJECT_DIR, "analysis_outputs", "Scenario_1_ThermalStandard_active_power.csv")
mkpath(dirname(out_path))
CSV.write(out_path, df_wide)
println("Saved to ", out_path)
```
6. File saved to `<PROJECT_DIR>/analysis_outputs/Scenario_1_ThermalStandard_active_power.csv`
7. Present: "73 thermal units, 744 hourly periods. Nuclear baseload at ~400 MW,
   combined-cycle units range 170-355 MW, peaking CTs dispatched during high-demand hours."
"""


@mcp.prompt()
def julia_coding_guide() -> str:
    """Julia code generation best practices for PowerAnalytics.jl scripts.

    Covers required imports, script structure, DataFrame conventions, type system,
    common patterns, chunked reading, and what to avoid.
    """
    return f"""\
## Julia Coding Guide for PowerAnalytics.jl

### Standard Imports

Always include this preamble at the top of every script:

```julia
{JULIA_PREAMBLE}```

> **Why each import matters:**
> - `using PowerSystems` — required for component types like `ThermalStandard`, `RenewableDispatch`
> - `using PowerSimulations` — required for `read_variable`, `list_variable_keys`, `get_timestamps`
> - `using PowerAnalytics` / `using PowerAnalytics.Metrics` — high-level metric functions
> - `using DataFrames`, `using CSV`, `using Dates` — data handling utilities

### Project Directory

The MCP server injects `PROJECT_DIR` into every script automatically.
**Use `PROJECT_DIR` instead of `@__DIR__`** — `@__DIR__` resolves to the temp file
directory, not your project root:

```julia
# CORRECT
output_dir = joinpath(PROJECT_DIR, "analysis_outputs")
mkpath(output_dir)
CSV.write(joinpath(output_dir, "results.csv"), df)

# WRONG — resolves to /tmp/jl_XXXXX/
output_dir = joinpath(@__DIR__, "analysis_outputs")
```

### Script Structure (Recommended: low-level `read_variable` path)

Every analysis script follows this pattern:
1. **Imports** (the preamble above)
2. **Load results** via `PowerSimulations.SimulationResults(path)` per scenario
3. **Get problem results** via `get_decision_problem_results(sr, "UC")`
4. **Read variables** via `read_variable(pr, VariableType, ComponentType)`
5. **Deduplicate** rolling-horizon overlap (see below)
6. **Output results**: print summary, save to CSV if large

### Low-Level Path (direct variable access, no OOM risk)

> **This is the recommended primary path.** It works reliably without needing
> a PowerSystems system JSON file attached to the results.

`read_variable` returns a `SortedDict{{DateTime, DataFrame}}` — one entry per execution step,
**not** a single DataFrame. Each sub-DataFrame has 3 columns in **long/tidy format**:
`DateTime`, `name` (component name), `value` (MW).

```julia
{JULIA_PREAMBLE}

path = "/path/to/scenario"
sr = PowerSimulations.SimulationResults(path)
pr = PowerSimulations.get_decision_problem_results(sr, "UC")

# List what's available (pretty-print verbose output)
vars = list_variable_keys(pr)
println("Available variables:")
for v in vars
    s = string(v)
    m = match(r"\\{{([^,]+),\\s*([^\\}}]+)\\}}", s)
    if m !== nothing
        var_name = split(m[1], ".")[end]
        comp_name = split(strip(m[2]), ".")[end]
        println("  ", var_name, " — ", comp_name)
    else
        println("  ", s)
    end
end

# Read one variable — returns SortedDict{{DateTime, DataFrame}}
raw = read_variable(pr, ActivePowerVariable, ThermalStandard)
println("Type: ", typeof(raw))
println("Execution steps: ", length(raw))

# Peek at one sub-DataFrame (long format: DateTime, name, value)
first_key = first(keys(raw))
println("\\nFirst execution step (", first_key, "):")
show(stdout, "text/plain", first(raw[first_key], 5))
```

### Rolling-Horizon Deduplication

Rolling-horizon simulations (e.g. 48h lookahead, daily execution) produce **overlapping**
data: hours 25–48 of day N overlap with hours 1–24 of day N+1. Without deduplication,
`vcat`-ing all sub-DataFrames produces duplicate timestamps and inflated statistics.

**Keep only the "realized" portion of each execution step** (from its start to the next
step's start):

```julia
# raw = read_variable(pr, ActivePowerVariable, ThermalStandard)
exec_times = sort(collect(keys(raw)))
step = exec_times[min(2, length(exec_times))] - exec_times[1]  # e.g. Day(1)
realized = DataFrame[]
for (i, t) in enumerate(exec_times)
    sub = copy(raw[t])
    t_next = i < length(exec_times) ? exec_times[i+1] : t + step
    filter!(row -> row.DateTime >= t && row.DateTime < t_next, sub)
    push!(realized, sub)
end
df_long = vcat(realized...)
println("Deduplicated rows: ", nrow(df_long))
println("Unique timestamps: ", length(unique(df_long.DateTime)))
```

### Pivoting from Long to Wide Format

After deduplication, pivot the long-format DataFrame to wide format for per-component
analysis:

```julia
# df_long has columns: DateTime, name, value
df_wide = unstack(df_long, :DateTime, :name, :value)
sort!(df_wide, :DateTime)
println("Wide shape: ", size(df_wide))
println("Columns: ", names(df_wide))
gen_cols = names(df_wide)[2:end]  # skip DateTime
```

### Chunked Reading for Large Datasets

Reading 30+ days × many generators in one call can cause OOM.
Process in weekly (or smaller) chunks:

```julia
{JULIA_PREAMBLE}

sr = PowerSimulations.SimulationResults("/path/to/scenario")
pr = PowerSimulations.get_decision_problem_results(sr, "UC")
exec_times = get_timestamps(pr)  # execution step starts, NOT hourly timestamps
start = first(exec_times)

all_chunks = DataFrame[]
for week in 0:3  # 4 weeks
    chunk_start = start + Day(7 * week)
    raw_chunk = read_variable(pr, ActivePowerVariable, ThermalStandard;
        initial_time=chunk_start, count=7*24)
    # raw_chunk is a SortedDict — concatenate its sub-DataFrames
    for (t, sub) in raw_chunk
        push!(all_chunks, sub)
    end
end
df_long = vcat(all_chunks...)
println("Combined long-format shape: ", size(df_long))
CSV.write(joinpath(PROJECT_DIR, "analysis_outputs", "thermal_active_power.csv"), df_long)
```

> **Note on `read_variable` time kwargs:**
> - Use `initial_time::DateTime` and `count::Int` (number of timesteps).
> - `count=7*24` means 168 hourly steps (one week). There is NO `end_time` parameter.
> - If `initial_time` falls mid-step, `count` measures from that timestamp.
>   Align `initial_time` to execution step starts (from `keys(raw)`) for predictable results.
> - If `count` exceeds available timesteps, the result contains only the available data (no error).

> **Note on `get_timestamps(pr)`:**
> Returns simulation execution starts (one per rolling-horizon solve, e.g. 31 daily starts),
> NOT the individual data timesteps (e.g. 744 hourly values). For the full time axis,
> use the `DateTime` column from `read_variable` after deduplication.

### DataFrame Conventions

**High-level path** (`calc_active_power` etc.) returns a **wide** DataFrame:
- First column is `DateTime` (hourly timestamps)
- Data columns named `TypeName__component_name` (e.g. `ThermalStandard__321_CC_1`)
- Access data columns: `names(df)[2:end]` (skip DateTime)
- Total across components: `sum(eachcol(df[!, names(df)[2:end]]))`

**Low-level path** (`read_variable` + `unstack`) returns **different** column names:
- After `unstack`, columns are just the component name (e.g. `321_CC_1`) — no type prefix
- To normalize for comparison with the high-level path:
  ```julia
  rename!(df_wide, [c => "ThermalStandard__$c" for c in gen_cols])
  ```

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
selector = make_selector(ThermalStandard, "321_CC_1")
```

### What NOT to Do
- Do NOT use `using Plots` or any plotting library (no display available)
- Do NOT use `@show` — use `println()` and `show(stdout, "text/plain", df)`
- Do NOT print entire large DataFrames — print `size(df)`, `first(df, 5)`, `last(df, 5)`
- Do NOT hardcode paths — use `PROJECT_DIR` or pass paths as variables
- Do NOT use `@__DIR__` — it resolves to the temp file directory, use `PROJECT_DIR` instead
- Do NOT omit the `scenarios` kwarg in `create_problem_results_dict` (high-level path only)
- Do NOT assume the high-level path (`compute(metric, ...)`) works without `set_system!`
- Do NOT use `typemax(DateTime)` for rolling-horizon dedup boundaries — use the step
  duration (e.g. `t + step`) to avoid including extra lookahead data

### High-Level Path (requires system JSON — use only if available)

> **WARNING:** The high-level path (`create_problem_results_dict` → `make_selector` →
> `compute(metric, results, selector)`) requires a PowerSystems system JSON file attached
> to the results via `set_system!(pr, "/path/to/system.json")`. Many simulation results
> directories do NOT include this file. **If your results only contain `simulation_store.h5`
> and metadata files, use the low-level `read_variable` path above instead.**

```julia
{JULIA_PREAMBLE}
results_dir = "/path/to/simulation_results"
results_all = create_problem_results_dict(
    results_dir, "UC";
    scenarios=["Scenario_1", "Scenario_2"],  # ALWAYS specify scenarios explicitly
)
results_uc = results_all["Scenario_1"]

# REQUIRED: attach system data (only if system.json exists)
# set_system!(results_uc, "/path/to/system.json")

selector = make_selector(ThermalStandard)
df = calc_active_power(selector, results_uc)
```

> **Critical: always pass `scenarios` explicitly.**
> Without it, `create_problem_results_dict` scans ALL subdirectories — including CSV
> output folders — and fails with "No valid simulation in ...csv" or
> "Found more than one simulation name" errors.

### Handling Large Outputs
If a DataFrame has many rows:
```julia
println("Shape: ", size(df))
println("Columns: ", names(df))
println("\\nFirst 5 rows:")
show(stdout, "text/plain", first(df, 5))
println("\\n\\nLast 5 rows:")
show(stdout, "text/plain", last(df, 5))
output_path = joinpath(PROJECT_DIR, "analysis_outputs", "output.csv")
mkpath(dirname(output_path))
CSV.write(output_path, df)
println("\\nFull data saved to ", output_path)
```
"""


@mcp.prompt()
def julia_error_handling() -> str:
    """Guide for iterating and debugging Julia script errors.

    Covers how to read Julia error messages, common PowerAnalytics pitfalls,
    the -32000 / OOM recovery workflow, iteration strategy, and when to give up.
    """
    return f"""\
## Julia Error Handling Guide

### MCP Error -32000 / "Connection closed" / Out of Memory

This is the most common production failure. It means the Julia subprocess was
killed by the OS (or ran out of memory) before it could return a result.

**Root cause:** Large data operations can exceed available memory and crash
the process. The MCP server now suppresses Julia's `[ Info: ]` log messages
to prevent stderr contamination of the JSON-RPC stream, which was the most
common cause of `-32000` errors.

**If you still see `-32000`:** The script may be too large or produce too much
output. Break it into smaller steps and save intermediate results to files.

**Use `read_variable` directly for reliable data access:**

```julia
{JULIA_PREAMBLE}

path = "/path/to/scenario"  # path to a single scenario directory
sr = PowerSimulations.SimulationResults(path)
pr = PowerSimulations.get_decision_problem_results(sr, "UC")

# Discover available variables (pretty-print verbose output)
vars = list_variable_keys(pr)
println("Available variables:")
for v in vars
    s = string(v)
    m = match(r"\\{{([^,]+),\\s*([^\\}}]+)\\}}", s)
    if m !== nothing
        var_name = split(m[1], ".")[end]
        comp_name = split(strip(m[2]), ".")[end]
        println("  ", var_name, " — ", comp_name)
    else
        println("  ", s)
    end
end

# Read a specific variable — returns SortedDict{{DateTime, DataFrame}}, NOT a single DataFrame
raw = read_variable(pr, ActivePowerVariable, ThermalStandard)
println("Execution steps: ", length(raw))

# Each sub-DataFrame has columns: DateTime, name, value (long format)
first_key = first(keys(raw))
println("\\nFirst sub-DataFrame (", first_key, "):")
show(stdout, "text/plain", first(raw[first_key], 5))
```

> **Important:** `read_variable` returns overlapping data from rolling-horizon solves.
> See the "Rolling-Horizon Deduplication" section in `julia_coding_guide` before computing
> statistics or totals.

**If even `read_variable` runs OOM, use chunked reading (see `julia_coding_guide`).**

**Prevent future OOM crashes:**
Set the `JULIA_MCP_MEMORY_LIMIT` environment variable (e.g. `"4G"`) before starting
the MCP server. This makes Julia raise a graceful `OutOfMemoryError` instead of being
killed silently.

**Note on `read_variable` kwargs:**
- `initial_time::DateTime` — start of the window
- `count::Int` — number of timesteps (e.g. `count=7*24` for one week of hourly data)
- There is NO `end_time` or `stop_time` parameter.

---

### Reading Julia Error Messages

**MethodError: no method matching func(::Type1, ::Type2)**
- You passed wrong argument types. Check the docstring for correct signature.
- Common cause: passing a string where a Type is expected (e.g. `"ThermalStandard"` instead of `ThermalStandard`).

**LoadError: UndefVarError: `name` not defined**
- Missing import. Add the appropriate `using` statement.
- Always include `using PowerSystems` when using component types.
- Always include `using PowerSimulations` when using `read_variable` / `list_variable_keys`.

**ArgumentError: ...**
- Wrong argument value. Read the full error message for expected values.
- Common cause: wrong problem_name or results_dir path.

**KeyError: key "Scenario_X" not found**
- The scenario name doesn't exist. List available keys first:
  `println(keys(results_all))`

**"No valid simulation in ...csv" or "Found more than one simulation name"**
- `create_problem_results_dict` scanned a non-simulation subdirectory (e.g. a CSV output folder).
- Fix: always pass `scenarios` explicitly:
  ```julia
  create_problem_results_dict(results_dir, "UC"; scenarios=["Scenario_1", "Scenario_2"])
  ```

**"ArgumentError: No system attached, need to call set_system!"**
- The high-level path (`compute(metric, results, selector)`) requires a PowerSystems system
  JSON file. Use `set_system!(pr, "/path/to/system.json")` before calling `compute`.
- **If no system JSON is available**, use the low-level `read_variable` path instead —
  it works without `set_system!`. See `julia_coding_guide` for the recommended pattern.

---

### Common PowerAnalytics Pitfalls

1. **Wrong component type name**: Use exact names from `poweranalytics://component-types`.
   Wrong: `Thermal`, `ThermalGenerator` — Right: `ThermalStandard`

2. **Metric returns empty DataFrame**: The component type has no results in this simulation.
   Check with `list_result_files` that the simulation ran successfully.

3. **Path not found**: Use `PROJECT_DIR` (injected by the MCP server) instead of `@__DIR__`
   or hardcoded paths.

4. **Out of memory**: See the -32000 section above. Use `read_variable` with chunked reading.

5. **`MethodError: no method matching size(::SortedDict...)`**: You called `size(df)` on
   the raw result of `read_variable`, which returns a `SortedDict{{DateTime, DataFrame}}`,
   not a single DataFrame. Use `length(raw)` for the number of execution steps, then
   access individual sub-DataFrames via `raw[key]`.

6. **More unique timestamps than expected**: You likely have rolling-horizon overlap.
   A 31-day simulation with 48h lookahead produces overlapping data for each execution
   step. Deduplicate using the pattern in `julia_coding_guide` — the last step boundary
   should use the step duration (e.g. `t + Day(1)`), NOT `typemax(DateTime)`, to avoid
   including extra lookahead hours.

---

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

### CRITICAL: Never save files inside the simulation results directory

`PowerSimulations.jl` recursively scans **all** subdirectories of the results folder
when loading simulations. If you save CSV files there, future calls will fail with:

- `"No valid simulation in ...csv"`
- `"Found more than one simulation name"`

**Always use a separate output directory.**

### Directory Structure

Save analysis outputs to a dedicated directory **outside** the simulation results:

```julia
# CORRECT: separate output directory
output_dir = joinpath(PROJECT_DIR, "analysis_outputs")
mkpath(output_dir)
CSV.write(joinpath(output_dir, "Scenario_1_ThermalStandard_active_power.csv"), df)

# WRONG: inside the simulation results directory
mkpath("{results_dir}/results")
CSV.write("{results_dir}/results/output.csv", df)  # This will break future loads!
```

> `PROJECT_DIR` is injected by the MCP server and points to your Julia project root.
> Use it instead of `@__DIR__` (which resolves to the temp file directory).

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
out_path = joinpath(PROJECT_DIR, "analysis_outputs", "output.csv")
mkpath(dirname(out_path))
CSV.write(out_path, df)
println("Results saved to ", out_path)
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
