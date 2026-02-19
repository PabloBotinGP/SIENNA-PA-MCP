#!/usr/bin/env julia
# build_sysimage.jl — Pre-compile a Julia sysimage containing PowerAnalytics
# and all its dependencies.  This eliminates ~15-30s of JIT compilation on
# every MCP tool call.
#
# Usage (from the Julia project root, e.g. ~/Documents/GPAC/Models/PowerAnalytics):
#
#   julia --project=. <path-to>/build_sysimage.jl [output_path]
#
# The resulting sysimage file can then be referenced via the PA_SYSIMAGE_PATH
# environment variable in .vscode/mcp.json.
#
# Typical build time: 5-15 minutes.  The output file is ~500 MB – 1 GB.

# Ensure PackageCompiler is available (it's a build-time-only tool; we add it
# to the current project if it isn't already present).
import Pkg
if !haskey(Pkg.project().dependencies, "PackageCompiler")
    @info "PackageCompiler not found in project — adding it now (build-time only)..."
    Pkg.add("PackageCompiler")
end
using PackageCompiler

# Packages to bake into the sysimage — must already be in the active project.
const PACKAGES = [
    :PowerSystems,
    :PowerSimulations,
    :StorageSystemsSimulations,
    :HydroPowerSimulations,
    :DataFrames,
    :Dates,
    :CSV,
    :PowerAnalytics,
]

# Default output path (next to the Julia project)
output = length(ARGS) >= 1 ? ARGS[1] : joinpath(@__DIR__, "pa_sysimage.so")

println("Building sysimage with packages: ", PACKAGES)
println("Output: ", output)
println()

# Optional: a precompile script that exercises the hot path so the JIT
# caches native code for the most common operations.
precompile_script = joinpath(@__DIR__, "precompile_workload.jl")
kwargs = Dict{Symbol,Any}()
if isfile(precompile_script)
    println("Using precompile workload: ", precompile_script)
    # precompile_execution_file runs a normal Julia script to warm the JIT;
    # precompile_statements_file expects raw `precompile(f, (...))` lines instead.
    kwargs[:precompile_execution_file] = [precompile_script]
end

create_sysimage(
    PACKAGES;
    sysimage_path = output,
    kwargs...,
)

println()
println("✓ Sysimage built successfully: ", output)
println("  Size: ", round(filesize(output) / 1024 / 1024; digits=1), " MB")
println()
println("To use it, set PA_SYSIMAGE_PATH in .vscode/mcp.json:")
println("  \"PA_SYSIMAGE_PATH\": \"$(output)\"")
