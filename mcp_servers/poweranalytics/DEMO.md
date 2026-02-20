# PowerAnalytics MCP Server — Interactive Demo

This document shows a realistic interaction between an LLM and the PowerAnalytics MCP server
using the dynamic agentic workflow.

---

## Demo Scenario

The user has two simulation scenarios saved in `_simulation_results_RTS/`:
- `Scenario_1/`: Baseline RTS-GMLC system
- `Scenario_2/`: RTS-GMLC with increased storage capacity

Both were simulated using PowerSimulations.jl unit commitment ("UC") model.

---

## Interaction 1: Check the environment

**User prompt:**
```
Check if the Julia environment is set up correctly.
```

**LLM action:**
```
Tool: check_julia_environment()
```

**Server response:**
```
Environment OK.
Julia version: 1.10.2
PowerAnalytics loaded successfully.
Project: /Users/pbotin/julia/projects/poweranalytics
```

**LLM response to user:**
> Julia environment is ready. Julia 1.10.2 with PowerAnalytics.jl is loaded.

---

## Interaction 2: Thermal generation analysis (full 7-step workflow)

**User prompt:**
```
Obtain the generation time series for each individual thermal component of the system.
```

**LLM reasoning:**
The user wants thermal generator output time series. Let me follow the 7-step workflow.

### Step 1: Check environment (already done above)

### Step 2: Read API index

**LLM reads resource:**
```
Resource: poweranalytics://api-index
```

Returns one-line summaries of all exported symbols. The LLM identifies:
- `create_problem_results_dict` — loads simulation results
- `make_selector` — creates component selector
- `calc_active_power` — computes active power time series

### Step 3: Read component types

**LLM reads resource:**
```
Resource: poweranalytics://component-types
```

Identifies `ThermalStandard` as the concrete type for thermal generators.

### Step 4: Get docstrings

**LLM action:**
```
Tool: get_docstring("calc_active_power", "PowerAnalytics.Metrics")
→ Returns full signature: calc_active_power(selector, results) → DataFrame

Tool: get_docstring("make_selector", "PowerAnalytics")
→ Returns full signature: make_selector(ComponentType) → ComponentSelector
```

### Step 5: Write and execute Julia script

**LLM action:**
```
Tool: run_julia_script(script="""
using PowerSystems, PowerSimulations, StorageSystemsSimulations
using HydroPowerSimulations, DataFrames, Dates, CSV
using PowerAnalytics, PowerAnalytics.Metrics

results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
scenario_key = first(keys(results_all))
println("Using scenario: ", scenario_key)
results_uc = results_all[scenario_key]

selector = make_selector(ThermalStandard)
df = calc_active_power(selector, results_uc)

println("Shape: ", size(df))
println("Columns: ", names(df))
println()
println("First rows:")
show(stdout, "text/plain", first(df, 5))
println()

mkpath("_simulation_results_RTS/results")
CSV.write("_simulation_results_RTS/results/Scenario_1_ThermalStandard_active_power.csv", df)
println("Saved to _simulation_results_RTS/results/Scenario_1_ThermalStandard_active_power.csv")
""")
```

**Server response:**
```
Using scenario: Scenario_1
Shape: (744, 77)
Columns: [:DateTime, :ThermalStandard__322_CT_6, :ThermalStandard__321_CC_1, ...]

First rows:
744x77 DataFrame
 Row | DateTime             ThermalStandard__322_CT_6  ThermalStandard__321_CC_1
-----+--------------------------------------------------------------------------
   1 | 2020-07-01T00:00:00                        0.0                    231.667
   2 | 2020-07-01T01:00:00                        0.0                    170.0
   3 | 2020-07-01T02:00:00                        0.0                    170.0

Saved to _simulation_results_RTS/results/Scenario_1_ThermalStandard_active_power.csv
```

### Steps 6-7: Save and present

**LLM response to user:**
> Retrieved thermal generation for 76 thermal units across July 2020 (744 hours).
>
> Key observations:
> - 76 individual ThermalStandard components in the system
> - Data spans 2020-07-01 to 2020-07-31 (744 hourly periods)
> - Some units (e.g., 322_CT_6) are never dispatched (0 MW throughout)
> - Combined-cycle unit 321_CC_1 ranges 170-355 MW
> - Nuclear baseload unit runs constantly at ~400 MW
> - Peak thermal generation occurs in afternoon/evening hours
>
> Full data saved to `_simulation_results_RTS/results/Scenario_1_ThermalStandard_active_power.csv`

---

## Interaction 3: Compare scenarios

**User prompt:**
```
How did the increased storage capacity in Scenario 2 affect thermal generation compared to Scenario 1?
```

**LLM reasoning:**
I need to compare generation across scenarios. I'll get the docstrings I need and write
a script that processes both scenarios.

**LLM action:**
```
Tool: run_julia_script(script="""
using PowerSystems, PowerSimulations, StorageSystemsSimulations
using HydroPowerSimulations, DataFrames, Dates, CSV, Statistics
using PowerAnalytics, PowerAnalytics.Metrics

results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
selector = make_selector(ThermalStandard)

thermal_by_scenario = Dict()
for (name, results_uc) in results_all
    df = calc_active_power(selector, results_uc)
    gen_cols = names(df)[2:end]
    df.total_thermal = sum(eachcol(df[!, gen_cols]))
    thermal_by_scenario[name] = df[!, [:DateTime, :total_thermal]]

    println("Scenario: ", name)
    println("  Total generation range: ",
            round(minimum(df.total_thermal); digits=1), " - ",
            round(maximum(df.total_thermal); digits=1), " MW")
    println("  Mean: ", round(mean(df.total_thermal); digits=1), " MW")
    println()
end

scenario1 = thermal_by_scenario["Scenario_1"].total_thermal
scenario2 = thermal_by_scenario["Scenario_2"].total_thermal
diff = scenario2 .- scenario1
println("Difference (Scenario 2 - Scenario 1):")
println("  Mean change: ", round(mean(diff); digits=1), " MW")
println("  Max reduction: ", round(minimum(diff); digits=1), " MW")
println("  Max increase: ", round(maximum(diff); digits=1), " MW")
""")
```

**Server response:**
```
Scenario: Scenario_1
  Total generation range: 8500.5 - 12000.3 MW
  Mean: 10200.7 MW

Scenario: Scenario_2
  Total generation range: 8100.2 - 11800.1 MW
  Mean: 9950.3 MW

Difference (Scenario 2 - Scenario 1):
  Mean change: -250.4 MW
  Max reduction: -800.2 MW
  Max increase: 150.1 MW
```

**LLM response to user:**
> The increased storage capacity in Scenario 2 significantly reduced thermal generation:
>
> | Metric | Scenario 1 | Scenario 2 | Change |
> |--------|-----------|-----------|--------|
> | Mean thermal | 10,200.7 MW | 9,950.3 MW | -250.4 MW (-2.5%) |
> | Peak thermal | 12,000.3 MW | 11,800.1 MW | -200.2 MW (-1.7%) |
>
> - Average reduction of 250 MW from increased storage capacity
> - Maximum displacement of 800 MW during peak demand hours
> - Some hours show slight increases (+150 MW) where storage charges
> - Nuclear baseload units unaffected; peaking CTs displaced most

---

## Interaction 4: Discover a new metric dynamically

**User prompt:**
```
What is the capacity factor of each renewable generator?
```

**LLM reasoning:**
I see `calc_capacity_factor` in the API index. Let me get its docstring and write a script.

**LLM action:**
```
Tool: get_docstring("calc_capacity_factor", "PowerAnalytics.Metrics")
→ Returns full docstring with signature and parameters
```

**LLM action:**
```
Tool: run_julia_script(script="""
using PowerSystems, PowerSimulations, StorageSystemsSimulations
using HydroPowerSimulations, DataFrames, Dates, CSV
using PowerAnalytics, PowerAnalytics.Metrics

results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
results_uc = results_all[first(keys(results_all))]

selector = make_selector(RenewableDispatch)
df = calc_capacity_factor(selector, results_uc)

println("Capacity factors:")
show(stdout, "text/plain", df; allcols=true)
println()

mkpath("_simulation_results_RTS/results")
CSV.write("_simulation_results_RTS/results/Scenario_1_RenewableDispatch_capacity_factor.csv", df)
println("Saved to _simulation_results_RTS/results/Scenario_1_RenewableDispatch_capacity_factor.csv")
""")
```

**LLM response to user:**
> The renewable fleet has an average capacity factor of 28.3%.
> Wind generators range from 22% to 35%, while solar peaks at 26%.
> Generator 'Wind_Farm_3' has the highest CF at 34.7%.
>
> Full data saved to `_simulation_results_RTS/results/Scenario_1_RenewableDispatch_capacity_factor.csv`

**Note:** No `calc_capacity_factor` tool was coded in Python. The LLM discovered it
from the auto-generated API index and learned its signature from the docstring.

---

## Summary

This demo shows the dynamic agentic workflow:

1. **Discover** — LLM reads the API index to find relevant functions
2. **Learn** — LLM pulls docstrings to understand exact signatures
3. **Compose** — LLM writes Julia scripts tailored to the task
4. **Execute** — LLM runs scripts and handles errors
5. **Present** — LLM summarizes with units and power systems context

No task-specific tools are needed in Python. The LLM adapts to any analysis that
PowerAnalytics.jl supports.
