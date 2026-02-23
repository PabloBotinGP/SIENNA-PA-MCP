# MCP Server Improvement Request
**Date:** 2026-02-20
**Context:** Empirically tested by running `get thermal generation time series for each individual thermal component` using the RTS Tutorial simulation results (31-day July 2020 UC simulation, 73 ThermalStandard generators, 48h lookahead horizon, Scenario_1 + Scenario_2).
**Method:** Because MCP tools were not available (see Issue 1), the equivalent Julia scripts were executed manually via shell, reproducing exactly what `run_julia_script` would have done.

---

## CRITICAL — Tool Injection / Connectivity

### Issue 1: MCP tools not available in Claude Code VSCode extension

**Observed:** The MCP server's `instructions` block was loaded (visible in system prompt) but **none of the server tools appeared** in the Claude Code tool set. Calling `ListMcpResourcesTool` returned `"No resources found"`. Calling `ReadMcpResourceTool` with `poweranalytics://api-index` returned `"MCP error -32000: Connection closed"`.

This means the entire intended workflow is blocked from the start — a user following the documented 7-step workflow cannot even reach Step 1 (`check_julia_environment`) because the tool simply isn't there.

**Suspected causes to investigate:**
- The server uses `FastMCP` with a `lifespan` context manager that runs Julia on startup. If Julia takes >N seconds, the MCP handshake may time out before tools are registered — even with a sysimage.
- The `poweranalytics://` URI scheme for resources may not be handled by the Claude Code MCP client's resource listing endpoint.
- There may be a stdout/stderr contamination issue: the `lifespan` block runs Julia subprocesses whose `[ Info: ... ]` log output could corrupt the MCP stdio stream if not cleanly separated.

**Suggested fixes:**
1. Add a startup health check log entry that does NOT run Julia — confirm the server starts and registers tools before attempting Julia auto-generation.
2. Make the `lifespan` auto-generation fully non-blocking: if sysimage is not present, skip entirely rather than logging warnings that could contaminate the stream.
3. Add a `README` section on verifying connectivity: "If tools don't appear in Claude Code, check [log location] and verify `pa_sysimage.so` is built."
4. Consider deferring Julia calls out of `lifespan` entirely — move auto-generation to first call of `check_julia_environment` or `refresh_api_index`.

---

## HIGH — Documentation / API Contract Bugs

### Issue 2: `read_variable` documented as returning `DataFrame` — actually returns `SortedDict{DateTime, DataFrame}`

**Location:** `server.py` fallback API index (line ~71), `julia_coding_guide` prompt (low-level example), `julia_error_handling` prompt.

**Observed:** `read_variable(pr, ActivePowerVariable, ThermalStandard)` returned:
```
DataStructures.SortedDict{DateTime, DataFrame, Base.Order.ForwardOrdering}
```
with 31 entries (one per daily UC execution step).

Calling `size(df)` immediately on this caused:
```
MethodError: no method matching size(::DataStructures.SortedDict{DateTime, DataFrame, ...})
```

**Impact:** Any script written from the current documentation fails on the first line after `read_variable`.

**Suggested fix — update all three locations with:**
```julia
# read_variable returns SortedDict{DateTime, DataFrame} — one entry per execution step
raw = read_variable(pr, ActivePowerVariable, ThermalStandard)
# typeof(raw) == SortedDict{DateTime, DataFrame, ForwardOrdering}
# length(raw) == number of execution steps (e.g. 31 for a 31-day simulation)
```

---

### Issue 3: Sub-DataFrames are long/tidy format — documentation implies wide format

**Location:** Fallback API index ("Returns DataFrame with DateTime column + one column per component (MW)"), `julia_coding_guide` (`names(df)[2:end]` pattern assumes wide), worked example in `analyze_simulation` prompt.

**Observed:** Each sub-DataFrame in the SortedDict has **3 columns**:
```
Row │ DateTime             name         value
    │ DateTime             String       Float64
```
NOT the wide format `[DateTime, 321_CC_1, 322_CT_6, ...]` that the documentation implies.

**Impact:** The `names(df)[2:end]` pattern to iterate generator columns fails; the entire statistics/summary section of any script written from docs produces wrong results.

**Suggested fix — add explicit pivot instructions to `julia_coding_guide`:**
```julia
# Step 1: Concatenate execution steps (keeping only realized dispatch)
exec_times = sort(collect(keys(raw)))
realized = DataFrame[]
for (i, t) in enumerate(exec_times)
    sub = copy(raw[t])
    t_next = i < length(exec_times) ? exec_times[i+1] : typemax(DateTime)
    filter!(row -> row.DateTime >= t && row.DateTime < t_next, sub)
    push!(realized, sub)
end
df_long = vcat(realized...)

# Step 2: Pivot to wide format
df_wide = unstack(df_long, :DateTime, :name, :value)
sort!(df_wide, :DateTime)
# Now: df_wide has columns [DateTime, 321_CC_1, 322_CT_6, ...]
gen_cols = names(df_wide)[2:end]
```

---

### Issue 4: Rolling-horizon duplication not documented anywhere

**Observed:** The UC problem uses a 48-hour lookahead horizon but runs daily. `read_variable` with no time filters returns ALL execution steps × full horizon:
- 31 steps × 48h × 73 generators = **108,624 long-format rows** (not 31 × 24 × 73 = 54,072)
- Each timestamp from hours 25–48 of a given day appears in BOTH that day's execution and the next day's execution
- The last execution (July 31) contributes 24 extra hours of August 1 lookahead

Without deduplication, a naive `vcat` produces **768 unique timestamps** instead of the expected **744** (and duplicate values for hours 1–24 of each day).

**Impact:** Summary statistics, capacity factors, and totals are wrong if duplication is not handled.

**Suggested fix:** Add a dedicated section to `julia_coding_guide` titled "Rolling-horizon deduplication" with the pattern above (keep `t >= exec_start && t < next_exec_start`). Also add a warning in the `julia_error_handling` prompt: "If you see more unique timestamps than expected, you likely have rolling-horizon overlap."

---

### Issue 5: Column naming inconsistency between high-level and low-level paths

**Observed:**
- `calc_active_power(make_selector(ThermalStandard), results)` → columns: `ThermalStandard__321_CC_1`
- `read_variable(pr, ActivePowerVariable, ThermalStandard)` + `unstack` → columns: `321_CC_1`

**Impact:** Code mixing both paths (e.g., comparing scenarios with different methods) produces column name mismatches that are hard to debug.

**Suggested fix:** Document this difference explicitly in `julia_coding_guide`. Also provide a one-liner to normalize: `rename!(df_wide, [c => "ThermalStandard__$c" for c in gen_cols])`.

---

### Issue 6: `get_timestamps(pr)` misleadingly returns execution cadence, not data resolution

**Observed:** `get_timestamps(pr)` returned 31 `DateTime` values (one per daily UC run), not 744 hourly values. The documentation and worked examples don't clarify this distinction.

**Impact:** Users writing `count = length(get_timestamps(pr)) * 24` get 744 — which happens to work — but for different reasons than they think. Users querying storage or other 5-minute resolution variables will be confused.

**Suggested fix:** Add a note: "`get_timestamps(pr)` returns the simulation execution starts (one per rolling-horizon solve), not the individual data timesteps within each solve. To get the full hourly time axis, use the `DateTime` column after `read_variable`."

---

## MEDIUM — Usability / Missing Features

### Issue 7: `using Statistics` missing from JULIA_PREAMBLE

**Location:** `server.py` JULIA_PREAMBLE constant (line ~291).

`using Statistics` is not included, but `mean`, `std`, `median` are needed in virtually every analysis. Any script computing average generation, capacity factors, or cost statistics will fail with `UndefVarError: mean not defined`.

**Suggested fix:** Add `using Statistics` to `JULIA_PREAMBLE`.

---

### Issue 8: Worked example in `analyze_simulation` uses `populate_system=true` as the primary path

**Location:** `analyze_simulation` prompt, "Worked Example: Thermal Generation Analysis" (Step 5 code block).

The canonical example uses `create_problem_results_dict(...; populate_system=true)` — the very option flagged throughout the documentation as causing OOM crashes. A new user following the "7-step workflow" example verbatim will likely hit a `-32000 / Connection closed` error on the first real simulation.

**Suggested fix:** Make the low-level `read_variable` path the primary worked example. Move `populate_system=true` to a secondary "high-level alternative" block with an explicit memory warning.

---

### Issue 9: `get_docstring` whitelist excludes `PowerSimulations`

**Location:** `server.py` `get_docstring` tool, `allowed_modules` set (line ~463).

The low-memory workflow relies on `PowerSimulations.read_variable`, `get_decision_problem_results`, `list_variable_keys`, and `get_timestamps` — none of which can be looked up via `get_docstring` because `PowerSimulations` is not in the allowed module list.

**Suggested fix:** Add `"PowerSimulations"` (and optionally `"PowerSystems"`, `"DataFrames"`) to `allowed_modules`. If there are security concerns about arbitrary module access, at minimum add `"PowerSimulations"` since it's the recommended fallback path.

---

### Issue 10: `list_variable_keys` output is hard to use

**Observed output:**
```
InfrastructureSystems.Optimization.VariableKey{ActivePowerVariable, ThermalStandard}("")
InfrastructureSystems.Optimization.VariableKey{EnergyVariable, EnergyReservoirStorage}("")
```

Users must mentally parse this to extract `ActivePowerVariable` and `ThermalStandard`. When the MCP server formats this output, it's even harder to read.

**Suggested fix:** In the `julia_coding_guide`, add a snippet to pretty-print variable keys:
```julia
vars = list_variable_keys(pr)
println("Available variables:")
for v in vars
    # Extract "ActivePowerVariable — ThermalStandard" from the verbose type string
    s = string(v)
    m = match(r"\{(\w+),\s*(\w+)\}", s)
    if m !== nothing
        println("  ", m[1], " — ", m[2])
    else
        println("  ", s)
    end
end
```

---

### Issue 11: No guidance on the `count` parameter edge cases

**Location:** `julia_coding_guide` chunked reading section, `julia_error_handling` prompt.

The docs say `count=7*24` for "one week of hourly data" but don't explain:
- What happens if `count` exceeds available timesteps (does it error or return partial?)
- How to compute `count` correctly for a rolling-horizon simulation (the "week" might overlap two execution steps)
- The interaction between `initial_time` and execution step boundaries

**Suggested fix:** Add a note: "If `initial_time` falls in the middle of a simulation day, `count` is measured from that exact timestamp. Safe usage: align `initial_time` to an execution step start (use `exec_times` from `keys(raw)`)."

---

## LOW — Minor Improvements

### Issue 12: `_format_result` puts stderr before stdout

**Location:** `server.py` `_format_result` function (line ~393).

Julia's `[ Info: ... ]` log messages go to stderr. With the current ordering, stderr is printed before stdout, so the output that Claude reads starts with log noise rather than the actual script output. This may cause the model to focus on Info messages rather than the data.

**Suggested fix:** Reorder to show stdout first, stderr last. Or filter out `[ Info: ]` lines from stderr (they're informational, not errors) before formatting.

---

### Issue 13: No end-to-end test script in the repository

There is no `tests/test_read_variable.jl` or equivalent that would catch the `SortedDict` return-type documentation bug. A simple integration test reading a known variable and asserting the return type would have caught Issues 2–5 before they reached users.

**Suggested addition:** `tests/test_low_memory_workflow.jl` that:
1. Loads a scenario
2. Calls `read_variable`
3. Asserts `typeof(result) <: AbstractDict`
4. Asserts each value has columns `[:DateTime, :name, :value]`
5. Performs the vcat + unstack + dedup pipeline
6. Asserts output shape matches expected (timesteps × generators)

---

## Summary Table

| # | Severity | Category | One-line description |
|---|----------|----------|----------------------|
| 1 | CRITICAL | Connectivity | MCP tools not injected into Claude Code |
| 2 | HIGH | Docs/API | `read_variable` returns SortedDict, not DataFrame |
| 3 | HIGH | Docs/API | Sub-DataFrames are long format, not wide |
| 4 | HIGH | Docs/API | Rolling-horizon duplication not documented |
| 5 | MEDIUM | Docs/API | Column naming inconsistency high-level vs low-level |
| 6 | MEDIUM | Docs/API | `get_timestamps` returns execution cadence, not data resolution |
| 7 | MEDIUM | Usability | `Statistics` missing from JULIA_PREAMBLE |
| 8 | MEDIUM | Usability | Worked example uses dangerous `populate_system=true` |
| 9 | MEDIUM | Usability | `get_docstring` can't look up `PowerSimulations` symbols |
| 10 | MEDIUM | Usability | `list_variable_keys` output hard to parse |
| 11 | LOW | Docs | No guidance on `count` parameter edge cases |
| 12 | LOW | UX | stderr before stdout in `_format_result` |
| 13 | LOW | Testing | No integration test for low-memory workflow |
