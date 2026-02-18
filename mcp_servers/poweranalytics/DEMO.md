# PowerAnalytics MCP Server — Interactive Demo

This document shows a realistic interaction between an LLM and the PowerAnalytics MCP server.

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

**LLM reasoning:**
The user wants to verify the setup. I should use the `check_julia_environment` tool.

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
```
✓ Julia environment is ready. Julia 1.10.2 with PowerAnalytics.jl is loaded.
```

---

## Interaction 2: Get thermal generation time series

**User prompt:**
```
Obtain the generation time series for each individual thermal component of the system.
```

**LLM reasoning:**
- The user wants thermal generator output time series
- PowerSystems.jl component type is `ThermalStandard`
- I should use the high-level `get_active_power_timeseries` tool
- The results are in `_simulation_results_RTS`
- The problem name is "UC" (unit commitment)
- First, let me check the API reference

**LLM reads resource:**
```
Resource: poweranalytics://api-reference
```
Returns function signatures and usage patterns.

**LLM action:**
```
Tool: get_active_power_timeseries(
  results_dir="_simulation_results_RTS",
  problem_name="UC",
  component_type="ThermalStandard",
  output_csv="results/thermal_generation.csv"
)
```

**Server-generated Julia script (internal):**
```julia
using PowerSystems
using PowerSimulations
using DataFrames, Dates, CSV
using PowerAnalytics
using PowerAnalytics.Metrics

# Load simulation results
results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)

# Select scenario (first one by default)
scenario_key = first(keys(results_all))
println("Using scenario: ", scenario_key)
results_uc = results_all[scenario_key]

# Create selector and compute active power
selector = make_selector(ThermalStandard)
df = calc_active_power(selector, results_uc)

# Output
println("Shape: ", size(df))
println("Columns: ", names(df))
println()
println("First rows:")
show(first(df, 5); allcols = true)
println()
println("Last rows:")
show(last(df, 5); allcols = true)
println()

CSV.write("results/thermal_generation.csv", df)
println("Results saved to results/thermal_generation.csv")
```

**Server response:**
```
Shape: (744, 77)
Columns: [:DateTime, :ThermalStandard__322_CT_6, :ThermalStandard__321_CC_1, ..., :ThermalStandard__107_CC_1]

First rows:
744×77 DataFrame
 Row │ DateTime             ThermalStandard__322_CT_6  ThermalStandard__321_CC_1  ⋯
─────┼──────────────────────────────────────────────────────────────────────────
   1 │ 2020-07-01T00:00:00                        0.0                    231.667  ⋯
   2 │ 2020-07-01T01:00:00                        0.0                    170.0    ⋯
   3 │ 2020-07-01T02:00:00                        0.0                    170.0    ⋯

Last rows:
744×77 DataFrame
   742 │ 2020-07-31T22:00:00                        0.0                    251.888  ⋯
   743 │ 2020-07-31T23:00:00                        0.0                    231.667  ⋯
   744 │ 2020-07-31T23:00:00                        0.0                    231.667  ⋯

Results saved to results/thermal_generation.csv
```

**LLM response to user:**
```
✓ Retrieved thermal generation time series for 76 thermal units across the entire month of July 2020 (744 hours).

Summary:
- 76 individual ThermalStandard components in the system
- Data spans 2020-07-01 to 2020-07-31 (744 hourly periods)
- Some units (e.g., ThermalStandard__322_CT_6) are never dispatched (0 MW throughout)
- Other units run frequently: ThermalStandard__321_CC_1 ranges 170–355 MW
- Baseload units (e.g., ThermalStandard__121_NUCLEAR_1) run constantly at ~400 MW
- Results saved to results/thermal_generation.csv for further analysis

Key observations:
- Peak thermal generation typically occurs in afternoon/evening hours
- Cycling units ramp up during high-demand periods
- Baseload nuclear unit provides constant ~400 MW supply
```

---

## Interaction 3: Compare scenarios

**User prompt:**
```
How did the increased storage capacity in Scenario 2 affect thermal generation compared to Scenario 1?
```

**LLM reasoning:**
- I need to compare generation across scenarios
- I should use the `compare_scenarios` prompt template first to understand the workflow
- Then call `run_julia_script` with a custom script that handles both scenarios

**LLM reads prompt:**
```
Prompt: compare_scenarios(component_type="ThermalStandard")
```

**LLM action:**
```
Tool: run_julia_script(script="""
using PowerSystems, PowerSimulations, DataFrames, Dates, CSV
using PowerAnalytics, PowerAnalytics.Metrics

results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
selector = make_selector(ThermalStandard)

thermal_by_scenario = Dict()
for (name, results_uc) in results_all
    df = calc_active_power(selector, results_uc)

    # Compute total thermal generation per timestep
    gen_cols = names(df)[2:end]  # skip DateTime
    df.total_thermal = sum(eachcol(df[!, gen_cols]))

    thermal_by_scenario[name] = df[!, [:DateTime, :total_thermal]]

    println("Scenario: ", name)
    println("  Total generation range: ",
            round(minimum(df.total_thermal); digits=1), " — ",
            round(maximum(df.total_thermal); digits=1), " MW")
    println("  Mean: ", round(mean(df.total_thermal); digits=1), " MW")
    println()
end

# Compare
scenario1 = thermal_by_scenario["Scenario_1"].total_thermal
scenario2 = thermal_by_scenario["Scenario_2"].total_thermal
diff = scenario2 .- scenario1
mean_reduction = mean(diff)

println("Difference (Scenario 2 - Scenario 1):")
println("  Mean change: ", round(mean_reduction; digits=1), " MW")
println("  Max reduction: ", round(minimum(diff); digits=1), " MW")
println("  Max increase: ", round(maximum(diff); digits=1), " MW")
println("  Std dev of changes: ", round(std(diff); digits=1), " MW")
""")
```

**Server response:**
```
Scenario: Scenario_1
  Total generation range: 8500.5 — 12000.3 MW
  Mean: 10200.7 MW

Scenario: Scenario_2
  Total generation range: 8100.2 — 11800.1 MW
  Mean: 9950.3 MW

Difference (Scenario 2 - Scenario 1):
  Mean change: -250.4 MW
  Max reduction: -800.2 MW
  Max increase: 150.1 MW
  Std dev of changes: 320.5 MW
```

**LLM response to user:**
```
✓ Comparison complete. The increased storage capacity in Scenario 2 significantly reduced thermal generation:

Key findings:
1. **Average reduction:** Thermal generation was 250 MW lower (−2.5%) with increased storage
2. **Peak reductions:** Maximum reduction of 800 MW during high-demand periods
3. **Night hours:** Some hours show slight increases (+150 MW) where storage supplies demand
4. **Variability:** Changes in thermal output vary by time of day (±320 MW std dev)

Economic impact:
- Reduced thermal generation typically means lower operating costs
- The storage facility absorbs peak loads and supplies them during lower-cost periods
- Nuclear baseload units still operate at full capacity (not affected by storage)
- Peaking units (CTs) are displaced more often in Scenario 2

Conclusion:
The increased energy reservoir capacity provides 250 MW of effective displacement of thermal generation,
improving system economics and likely reducing emissions (depending on coal/gas mix).
```

---

## Interaction 4: Discover result files

**User prompt:**
```
What result files are available?
```

**LLM action:**
```
Tool: list_result_files(directory="_simulation_results_RTS")
```

**Server response:**
```
Files in _simulation_results_RTS (pattern: *):
  Scenario_1/simulation_store.h5  (245.3 MB)
  Scenario_1/system_snapshots.h5  (15.2 MB)
  Scenario_2/simulation_store.h5  (248.1 MB)
  Scenario_2/system_snapshots.h5  (15.4 MB)
  results/thermal_generation.csv  (2.1 MB)
  results/Scenario_1_ThermalStandard_active_power.csv  (1.2 MB)
  results/Scenario_2_ThermalStandard_active_power.csv  (1.3 MB)
```

**LLM response:**
```
✓ Available files:

Simulation results (binary HDF5):
- Scenario_1/ and Scenario_2/: Complete simulation outputs (simulation_store.h5)
- System definitions: PowerSystems.jl snapshots (system_snapshots.h5)

Exported analysis:
- thermal_generation.csv: Thermal unit output time series
- Scenario-specific thermal results: 1.2–1.3 MB each
```

---

## Interaction 5: Custom analysis (escape hatch)

**User prompt:**
```
What's the average dispatch cost across all generators? And which thermal units have the highest average output?
```

**LLM reasoning:**
- Cost data and dispatch optimization details aren't exposed by the high-level tool
- I need to use `run_julia_script` with a custom script to access auxiliary variables
- I'll read the API reference first to understand what's available

**LLM reads resource:**
```
Resource: poweranalytics://api-reference
```

**LLM action (generates custom script):**
```
Tool: run_julia_script(script="""
using PowerSystems, PowerSimulations, DataFrames, Dates
using PowerAnalytics, PowerAnalytics.Metrics

results_all = create_problem_results_dict("_simulation_results_RTS", "UC"; populate_system = true)
results_uc = first(values(results_all))

# Get thermal generation
selector = make_selector(ThermalStandard)
gen_df = calc_active_power(selector, results_uc)

# Compute average generation per unit
gen_cols = names(gen_df)[2:end]
avg_gen = vec(mean.(eachcol(gen_df[!, gen_cols])))
top_units = sortperm(avg_gen; rev=true)[1:5]

println("Top 5 thermal units by average generation:")
for (i, idx) in enumerate(top_units)
    unit_name = gen_cols[idx]
    println("$(i). $unit_name: $(round(avg_gen[idx]; digits=1)) MW")
end

# Note: Dispatch costs from dual variables require accessing
# the optimization problem auxiliary variables, which are available
# but require deeper PowerSimulations.jl API knowledge
println()
println("Note: Detailed dispatch cost data requires direct access to")
println("optimization solver dual variables. Use PowerSimulations.jl API to query.")
""")
```

**Server response:**
```
Top 5 thermal units by average generation:
1. ThermalStandard__121_NUCLEAR_1: 398.5 MW
2. ThermalStandard__321_CC_1: 245.2 MW
3. ThermalStandard__315_STEAM_1: 156.8 MW
4. ThermalStandard__123_STEAM_2: 148.3 MW
5. ThermalStandard__102_STEAM_4: 142.1 MW

Note: Detailed dispatch cost data requires direct access to
optimization solver dual variables. Use PowerSimulations.jl API to query.
```

**LLM response:**
```
✓ Analysis complete.

Top thermal generators (by average dispatch):
1. **Nuclear (121):** 398.5 MW — runs as baseload, nearly constant output
2. **Combined cycle (321):** 245.2 MW — primary intermediate load unit
3. **Steam units (315, 123, 102):** 156–148 MW — fill peak/shoulder loads

Dispatch cost analysis:
The high-level tools don't directly expose cost data. To get detailed dispatch costs
per unit, you would need to:
1. Access the PowerSimulations.jl optimization dual variables
2. Query the HDF5 store directly for constraint shadow prices

Would you like me to write a custom script using PowerSimulations.jl to extract that information?
```

---

## Summary

This demo shows the three levels of interaction:

1. **High-level tools** (Option C): `get_active_power_timeseries` — the LLM passes parameters, tool generates script
2. **Template prompts** (Option B): `analyze_generation`, `compare_scenarios` — guide the LLM, reduce hallucination
3. **Escape hatch** (Option A): `run_julia_script` — for custom analysis beyond the high-level tools

The workflow prevents hallucination by:
- Starting with high-level, validated tools for common queries
- Providing resources (API reference, component types) before the LLM writes custom code
- Using templates to guide standard analyses
- Only allowing raw Julia code when necessary
