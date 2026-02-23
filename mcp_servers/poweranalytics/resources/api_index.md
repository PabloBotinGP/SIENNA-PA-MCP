## PowerAnalytics

- `AGG_META_KEY` [Const]: ```
- `ComponentSelector` [Type]: Given some [`ComponentContainer`](@ref)-like source of components to draw from, such as a [`PowerSystems.System`](@ex...
- `ComponentSelectorTimedMetric` [Type]: [`TimedMetric`](@ref)s defined in terms of a `ComponentSelector`.
- `ComponentTimedMetric` [Type]: ```
- `CustomTimedMetric` [Type]: ```
- `DATETIME_COL` [Const]: ```
- `META_COL_KEY` [Const]: ```
- `Metric` [Type]: A PowerAnalytics `Metric` specifies how to compute a useful quantity, like active power or curtailment, from a set of...
- `RESULTS_COL` [Const]: ```
- `ResultsTimelessMetric` [Type]: ```
- `SYSTEM_COL` [Const]: ```
- `SystemTimedMetric` [Type]: ```
- `TimedMetric` [Type]: [`Metric`](@ref)s that return time series.
- `TimelessMetric` [Type]: [`Metric`](@ref)s that do not return time series.
- `aggregate_time` [Function]: ```julia
- `categorize_data` [Function]: ```julia
- `compose_metrics` [Function]: Given a list of metrics and a function that applies to their results to produce one result, create a new metric that ...
- `compute` [Function]: The `compute` function is the most important part of the [`Metric`](@ref) interface. Calling a metric as if it were a...
- `compute_all` [Function]: `compute_all` takes several metrics, single-group `ComponentSelector`s if relevant, and optionally column names and p...
- `create_problem_results_dict` [Function]: ```julia
- `get_agg_meta` [Function]: ```julia
- `get_component_agg_fn` [Function]: No documentation found for public symbol.
- `get_data_cols` [Function]: ```julia
- `get_data_df` [Function]: ```julia
- `get_data_mat` [Function]: ```julia
- `get_data_vec` [Function]: ```julia
- `get_generation_data` [Function]: No documentation found for public symbol.
- `get_load_data` [Function]: No documentation found for public symbol.
- `get_name` [Function]: ```julia
- `get_service_data` [Function]: No documentation found for public symbol.
- `get_time_agg_fn` [Function]: No documentation found for public symbol.
- `get_time_df` [Function]: ```julia
- `get_time_vec` [Function]: ```julia
- `hcat_timed_dfs` [Function]: ```julia
- `is_col_meta` [Function]: ```julia
- `make_fuel_dictionary` [Function]: ```julia
- `make_selector` [Function]: Factory function to create the appropriate subtype of [`ComponentSelector`](@ref) given the arguments. Users should c...
- `mean` [Function]: ```
- `metric_selector_to_string` [Function]: ```julia
- `no_datetime` [Function]: No documentation found for public symbol.
- `parse_generator_categories` [Function]: ```julia
- `parse_generator_mapping_file` [Function]: ```julia
- `parse_injector_categories` [Function]: ```julia
- `rebuild_metric` [Function]: ```julia
- `set_agg_meta!` [Function]: ```julia
- `set_col_meta!` [Function]: ```julia
- `unweighted_sum` [Function]: ```julia
- `weighted_mean` [Function]: ```julia

## PowerAnalytics.Metrics

- `calc_active_power` [Const]: ```
- `calc_active_power_forecast` [Const]: ```
- `calc_active_power_in` [Const]: ```
- `calc_active_power_out` [Const]: ```
- `calc_capacity_factor` [Const]: ```
- `calc_curtailment` [Const]: ```
- `calc_curtailment_frac` [Const]: ```
- `calc_discharge_cycles` [Const]: ```
- `calc_integration` [Const]: ```
- `calc_is_slack_up` [Const]: ```
- `calc_load_forecast` [Const]: ```
- `calc_load_from_storage` [Const]: ```
- `calc_net_load_forecast` [Const]: ```
- `calc_production_cost` [Const]: ```
- `calc_shutdown_cost` [Const]: ```
- `calc_startup_cost` [Const]: ```
- `calc_stored_energy` [Const]: ```
- `calc_sum_bytes_alloc` [Const]: ```
- `calc_sum_objective_value` [Const]: ```
- `calc_sum_solve_time` [Const]: ```
- `calc_system_load_forecast` [Const]: ```
- `calc_system_load_from_storage` [Const]: ```
- `calc_system_slack_up` [Const]: ```
- `calc_total_cost` [Const]: ```

## PowerAnalytics.Selectors

- `all_loads` [Const]: [`ComponentSelector`](@ref) represented by a type of component. Contains all the components of that type, grouped by ...
- `all_storage` [Const]: [`ComponentSelector`](@ref) represented by a type of component. Contains all the components of that type, grouped by ...
- `categorized_generators` [Const]: [`ComponentSelector`](@ref) represented by a list of other `ComponentSelector`s. Those selectors form the groups.
- `categorized_injectors` [Const]: [`ComponentSelector`](@ref) represented by a list of other `ComponentSelector`s. Those selectors form the groups.
- `generator_categories` [Const]: ```
- `injector_categories` [Const]: ```

