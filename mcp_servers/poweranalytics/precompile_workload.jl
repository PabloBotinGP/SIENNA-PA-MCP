# precompile_workload.jl — Exercises the hot path so PackageCompiler caches
# native code for the most common operations.  This file is automatically
# picked up by build_sysimage.jl if present.
#
# It is intentionally a no-op at the data level (we don't need real simulation
# results), but it forces the JIT to compile the critical method specialisations.

using PowerSystems
using PowerSimulations
using StorageSystemsSimulations
using HydroPowerSimulations
using DataFrames
using Dates
using CSV
using PowerAnalytics
using PowerAnalytics.Metrics

# Force compilation of DataFrame construction
df = DataFrame(DateTime = DateTime[], value = Float64[])

# Force compilation of CSV write path
io = IOBuffer()
CSV.write(io, df)

println("Precompile workload complete.")
