# Implementation Plan: Dynamic Agentic PowerAnalytics MCP Server

## Context

The current MCP server has hardcoded tools (like `get_active_power_timeseries`) and static resources (hand-written API reference strings). This means every new analysis task requires a new tool to be coded. PowerAnalytics.jl actually exports **39 symbols**, **25 built-in metrics**, and **8 built-in selectors** — but the server only exposes one metric through one tool.

The redesign replaces this with a dynamic "index → docstring → generate → execute" workflow. The LLM discovers the API at runtime, pulls detailed docs on demand, writes its own Julia scripts, and executes them. No new Python code needed for new analysis tasks.

## Architecture: Before → After

| Aspect | Current | New |
|--------|---------|-----|
| Tools | 4 (one hardcoded per-task) | 5 (generic, reusable) |
| Resources | 2 (static strings) | 2 (auto-generated from Julia) |
| Prompts | 2 (task-specific templates) | 1 (full orchestration workflow) |
| Adding new analysis | Write new Python tool | LLM figures it out from docs |

## Key Design Decisions

1. **API index cached at startup** — Julia API doesn't change during a session. Two Julia calls at startup (~4-6s total, run in parallel), cached in memory. `refresh_api_index` tool for manual refresh.

2. **`get_docstring` as a tool, not a resource template** — Resource templates aren't reliably called by all MCP clients. A tool is universally callable. Cost: ~2-3s per call with sysimage, but LLM typically needs 1-3 docstrings per task.

3. **Remove `get_active_power_timeseries`** — It's the exact pattern the new architecture eliminates. The worked example in the orchestration prompt shows how the LLM achieves the same result dynamically.

4. **Persistent Julia REPL deferred** — Sysimage already brings latency to 2-3s/call. A persistent REPL adds complexity (process lifecycle, state isolation, crash recovery) for marginal gain. Revisit if latency becomes a pain point.

5. **Fallback to current hardcoded text** — If Julia fails at startup, the old static text is used as fallback so the server still works.

---

## Implementation Phases

### Phase 1: API cache + lifespan + new resources
**File: `server.py`**

- Add module-level `_api_cache` dict and `asyncio.Event` for readiness
- Add `API_INDEX_SCRIPT` constant — Julia script that iterates `names(PowerAnalytics)`, `names(PowerAnalytics.Metrics)`, `names(PowerAnalytics.Selectors)` and prints one-line-per-symbol index using `Base.doc()` first sentence
- Add `COMPONENT_TYPES_SCRIPT` constant — Julia script that uses `subtypes()` to enumerate PowerSystems.jl concrete component types
- Add `_initialize_api_cache()` async function — runs both scripts in parallel via `asyncio.gather`, stores results, falls back to hardcoded text on failure
- Add `server_lifespan` async context manager — calls `_initialize_api_cache()` on startup
- Update `FastMCP(...)` constructor to pass `lifespan=server_lifespan`
- Replace `get_api_reference()` → `get_api_index()` (reads from cache)
- Replace `get_component_types()` (reads from cache instead of returning static string)
- Keep old hardcoded strings as `_FALLBACK_API_INDEX` and `_FALLBACK_COMPONENT_TYPES`

### Phase 2: `get_docstring` tool
**File: `server.py`**

- New `get_docstring(symbol_name, module_name="PowerAnalytics")` tool
- Input validation: `symbol_name.isidentifier()` check, `module_name` whitelist (`PowerAnalytics`, `PowerAnalytics.Metrics`, `PowerAnalytics.Selectors`)
- Generates Julia script: `Base.doc(getfield(module, Symbol(name)))`
- Returns full docstring text or clear error message

### Phase 3: `refresh_api_index` tool
**File: `server.py`**

- New `refresh_api_index()` tool — clears cache, re-runs `_initialize_api_cache()`, returns symbol count

### Phase 4: New orchestration prompt + remove old tools/prompts
**File: `server.py`**

- **Delete** `get_active_power_timeseries` function entirely
- **Delete** `analyze_generation` and `compare_scenarios` prompts
- **Add** `analyze_simulation(task_description, results_dir, problem_name)` prompt with:
  - The 7-step workflow (check env → read index → read component types → get docstrings → write script → execute & save → analyze & present)
  - A worked example showing thermal generation analysis
  - Conventions for saving results, handling errors, presenting with units
- **Update** `instructions` in `FastMCP(...)` to describe the new workflow

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
  - `test_analyze_simulation_prompt` — new prompt contains workflow steps
  - `test_api_index_resource` — new resource returns cached content
  - `test_component_types_resource` — new resource returns cached content
- Final count: ~19 tests (was 15, minus 6, plus 10)

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

**Prompts (1):**
| Prompt | Status |
|--------|--------|
| `analyze_simulation` | **New** (replaces 2 old prompts) |

## Verification Plan

1. **Unit tests**: Run `.venv/bin/pytest tests/ -v` — all ~19 tests pass
2. **Manual smoke test from Claude Code**:
   - `/mcp` to reload server, verify poweranalytics appears with 5 tools
   - Call `check_julia_environment` — should pass
   - Read `poweranalytics://api-index` resource — should show auto-generated symbol list
   - Call `get_docstring("calc_active_power", "PowerAnalytics.Metrics")` — should return full docstring
   - Ask "Get thermal generation for the RTS system" — LLM should follow the 7-step workflow autonomously
3. **Fallback test**: Temporarily set `PA_PROJECT_PATH` to invalid path, restart server — resources should fall back to hardcoded text
