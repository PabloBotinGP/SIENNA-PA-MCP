# PowerAnalytics MCP Server — LLM Evaluation Prompts

Use these prompts to verify the MCP server is working end-to-end.
Copy one prompt at a time into the Copilot chat panel (or any MCP-enabled LLM chat)
and check that the response matches the expected behaviour described below.

---

## 1. Environment Check (smoke test)

**Prompt:**
> Verify that the PowerAnalytics Julia environment is set up correctly.

**Expected behaviour:**
- The LLM calls `check_julia_environment`.
- Response includes Julia version (1.11.x) and "PowerAnalytics loaded successfully."
- No errors about missing packages.

---

## 2. Discover Available Results

**Prompt:**
> List the simulation result files available under `_simulation_results_RTS`.

**Expected behaviour:**
- The LLM calls `list_result_files` with `directory` pointing to the results folder.
- Response lists at least `Scenario_1/data_store/simulation_store.h5` and
  `Scenario_2/data_store/simulation_store.h5`.

---

## 3. Thermal Generation Time Series (core tool)

**Prompt:**
> Obtain the generation time series for each individual thermal component of the
> system, using `_simulation_results_RTS` Scenario_1. Summarise the results.

**Expected behaviour:**
- The LLM calls `get_active_power_timeseries` with `component_type="ThermalStandard"`,
  `problem_name="UC"`, `results_dir="_simulation_results_RTS"`, `scenario="Scenario_1"`.
- Response reports a DataFrame of shape **(744, 74)** — 744 hours × 73 generators + DateTime.
- The LLM identifies baseload units (e.g. `121_NUCLEAR_1` at 400 MW), cycling CTs,
  and CC / STEAM units with varying dispatch levels.

---

## 4. Renewable Generation

**Prompt:**
> Show me the active power output for all dispatchable renewable generators
> in Scenario_1 of `_simulation_results_RTS`.

**Expected behaviour:**
- The LLM calls `get_active_power_timeseries` with `component_type="RenewableDispatch"`.
- Response shows a DataFrame with renewable generator columns and MW values.

---

## 5. Scenario Comparison

**Prompt:**
> Compare the total thermal generation between Scenario_1 and Scenario_2
> in `_simulation_results_RTS`. Which scenario has lower thermal output and why?

**Expected behaviour:**
- The LLM either calls `get_active_power_timeseries` twice (once per scenario)
  or uses `run_julia_script` with a custom comparison script.
- Response identifies that Scenario_2 (10× storage) displaces some thermal generation,
  leading to lower total thermal MW.

---

## 6. Custom Julia Script (advanced)

**Prompt:**
> Write and execute a Julia script that computes the capacity factor
> for each thermal generator in Scenario_1 of `_simulation_results_RTS`.
> A generator's capacity factor is its mean output divided by its maximum
> rated capacity (Pmax). Print the top-10 generators by capacity factor.

**Expected behaviour:**
- The LLM reads `poweranalytics://api-reference` and/or `poweranalytics://component-types`.
- Calls `run_julia_script` with a script that loads results, computes capacity factors,
  and prints a sorted table.
- Response includes a ranked list with generator names and capacity factor percentages.

---

## 7. Error Recovery

**Prompt:**
> Get the active power for component type "FakeComponent" in Scenario_1
> of `_simulation_results_RTS`.

**Expected behaviour:**
- The LLM calls `get_active_power_timeseries` with `component_type="FakeComponent"`.
- Julia returns an error (no such type).
- The LLM explains the error and suggests valid component types
  (ThermalStandard, RenewableDispatch, etc.).

---

## Scoring Rubric

| # | Criterion | Pass |
|---|-----------|------|
| 1 | Environment check succeeds | Julia version + "loaded successfully" |
| 2 | Result files discovered | Both scenarios listed |
| 3 | Thermal time series returned | Shape (744, 74), generator names visible |
| 4 | Renewable time series returned | Valid DataFrame with MW values |
| 5 | Scenario comparison meaningful | Identifies storage impact on thermal dispatch |
| 6 | Custom script executes | Capacity factors computed and ranked |
| 7 | Error handled gracefully | Explains error, suggests alternatives |
