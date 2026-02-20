# PowerAnalytics MCP Server — Agentic Workflow

## Overview

The PowerAnalytics MCP server enables an LLM to autonomously analyze power system simulation results by dynamically discovering the PowerAnalytics.jl API, composing Julia scripts, and executing them — all without requiring pre-built, task-specific tools.

Instead of hardcoding one tool per analysis task, the server provides:
- An **auto-generated API index** so the LLM knows what functions exist
- A **docstring retrieval tool** so the LLM can read detailed documentation on demand
- A **Julia script execution tool** so the LLM can run any analysis it designs

This means new analysis capabilities require **zero server-side code changes**.

---

## The 7-Step Workflow

When a user asks for an analysis (e.g., "Compare thermal generation costs across scenarios"), the LLM follows this workflow:

```
┌─────────────────────────────────────────────────────────┐
│  User: "Compare thermal generation costs across         │
│         scenarios in the RTS system"                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 1: CHECK ENVIRONMENT                              │
│  Tool: check_julia_environment()                        │
│  → Verifies Julia is installed, PowerAnalytics loads,   │
│    and the project path is valid.                       │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 2: READ API INDEX                                 │
│  Resource: poweranalytics://api-index                   │
│  → Auto-generated one-line summary of every exported    │
│    function, type, and constant across:                 │
│    - PowerAnalytics (39 symbols)                        │
│    - PowerAnalytics.Metrics (25 metrics)                │
│    - PowerAnalytics.Selectors (8 selectors)             │
│                                                         │
│  The LLM scans this index and identifies which symbols  │
│  are relevant to the user's request. For this task:     │
│  → create_problem_results_dict, make_selector,          │
│    calc_production_cost, calc_active_power               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 3: READ COMPONENT TYPES                           │
│  Resource: poweranalytics://component-types             │
│  → Auto-generated list of PowerSystems.jl component     │
│    types (ThermalStandard, RenewableDispatch, etc.)     │
│    so the LLM knows what types to query.                │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 4: GET DETAILED DOCSTRINGS                        │
│  Tool: get_docstring(symbol, module)                    │
│  → Pulls the full Julia docstring for each function     │
│    the LLM identified in Step 2.                        │
│                                                         │
│  Example calls:                                         │
│  get_docstring("create_problem_results_dict",           │
│                "PowerAnalytics")                        │
│  get_docstring("calc_production_cost",                  │
│                "PowerAnalytics.Metrics")                │
│  get_docstring("make_selector",                         │
│                "PowerAnalytics")                        │
│                                                         │
│  Each call returns the full signature, argument         │
│  descriptions, return types, and usage examples.        │
│  This prevents hallucination of non-existent APIs.      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 5: WRITE AND EXECUTE JULIA SCRIPT                 │
│  Tool: run_julia_script(script)                         │
│  → The LLM composes a complete Julia script based on    │
│    the docstrings it read. The script:                  │
│    - Loads simulation results                           │
│    - Creates component selectors                        │
│    - Computes metrics                                   │
│    - Prints summary statistics to stdout                │
│                                                         │
│  If the script fails, the LLM reads the error message,  │
│  fixes the script, and retries.                         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 6: SAVE RESULTS                                   │
│  Convention: results/{scenario}_{type}_{metric}.csv     │
│  → The LLM includes CSV.write() in the script to save  │
│    DataFrames to disk with descriptive filenames.       │
│  → Tool: list_result_files() can verify saved output.   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 7: ANALYZE AND PRESENT                            │
│  → The LLM interprets results in power systems context: │
│    - "Scenario 2 reduced thermal costs by 12% ($2.3M)"  │
│    - "Storage displaced 250 MW of peak thermal gen"     │
│    - "Curtailment increased from 3% to 7%"             │
│  → All values include units (MW, MWh, $/MWh)           │
│  → Trends and anomalies are highlighted                 │
└─────────────────────────────────────────────────────────┘
```

---

## Why This Design Works

### Context Window Efficiency
The API index is a compact listing (~2-3 KB) with one line per symbol. The LLM reads this once, then pulls full docstrings only for the 2-5 functions it actually needs (~1-2 KB each). This avoids dumping all 146 docstrings (~50+ KB) into context.

```
Traditional approach:  Load all docs upfront     → ~50 KB in context
This approach:         Index (3 KB) + 3 docs (5 KB) → ~8 KB in context
                       Savings: ~84% token reduction
```

### Zero-Maintenance API Coverage
When PowerAnalytics.jl adds new functions or metrics, the server automatically picks them up on next restart — no Python code changes needed. The index regenerates from the installed package.

### Grounded Code Generation
The LLM never guesses API signatures. It reads the actual Julia docstrings before writing any code. This eliminates hallucination of non-existent functions, wrong argument orders, or incorrect types.

### Graceful Degradation
If Julia fails at startup (wrong path, missing packages), the server falls back to hardcoded static text that covers the most common functions. The server never refuses to start.

---

## MCP Components Summary

### Tools (what the LLM can do)

| Tool | Purpose | When Used |
|------|---------|-----------|
| `check_julia_environment` | Verify Julia + packages are installed | Step 1 (always first) |
| `get_docstring` | Pull full docstring for a specific symbol | Step 4 (on demand) |
| `run_julia_script` | Execute any Julia code | Step 5 (core action) |
| `list_result_files` | Discover simulation results and saved files | Steps 2, 6 (discovery) |
| `refresh_api_index` | Force-regenerate cached API index | Rare (after package update) |

### Resources (what the LLM can read)

| Resource URI | Content | Size |
|-------------|---------|------|
| `poweranalytics://api-index` | One-line summary of all exported symbols | ~2-3 KB |
| `poweranalytics://component-types` | PowerSystems.jl component type hierarchy | ~1-2 KB |

### Prompts (master + 4 specialized sub-prompts)

| Prompt | Purpose | When Used |
|--------|---------|-----------|
| `analyze_simulation` | Master orchestration — the 7-step workflow with worked example | Entry point for every analysis task |
| `julia_coding_guide` | Script structure, imports, DataFrame conventions, common pitfalls | Step 5 (before writing Julia code) |
| `julia_error_handling` | Reading errors, retry strategy, common PowerAnalytics pitfalls | Step 5 (when a script fails) |
| `output_saving_conventions` | File naming, directory structure, when to save vs print | Step 6 (saving results) |
| `results_presentation` | Units, precision, summarization rules, power systems context | Step 7 (presenting to user) |

The master prompt references the sub-prompts by name. The LLM reads each one when it reaches the relevant step, keeping context usage efficient — only the guidance needed for the current step is loaded.

---

## Example Interaction

**User:** "What is the capacity factor of each renewable generator?"

**LLM workflow:**

1. Calls `check_julia_environment()` → OK
2. Reads `poweranalytics://api-index` → finds `calc_capacity_factor` in Metrics module
3. Reads `poweranalytics://component-types` → identifies `RenewableDispatch`
4. Calls `get_docstring("calc_capacity_factor", "PowerAnalytics.Metrics")` → gets full signature
5. Calls `get_docstring("make_selector", "PowerAnalytics")` → gets selector docs
6. Writes and executes Julia script:

```julia
using PowerAnalytics, PowerSystems, DataFrames, CSV
# ... (standard preamble)

results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
results_uc = results_all[first(keys(results_all))]

selector = make_selector(RenewableDispatch)
df = calc_capacity_factor(selector, results_uc)

println("Capacity factors:")
show(df; allcols = true)
CSV.write("results/renewable_capacity_factor.csv", df)
```

7. Presents results:
   > "The renewable fleet has an average capacity factor of 28.3%.
   > Wind generators range from 22% to 35%, while solar peaks at 26%.
   > Generator 'Wind_Farm_3' has the highest CF at 34.7%..."

**Note:** No `calc_capacity_factor` tool was coded in Python. The LLM discovered it from the auto-generated index and learned its API from the docstring.
