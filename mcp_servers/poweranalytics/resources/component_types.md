# PowerSystems.jl Component Types

Concrete component types available for use with `make_selector()`:

## Generators
- `HydroDispatch`
- `HydroPumpTurbine`
- `HydroTurbine`
- `RenewableDispatch`
- `RenewableNonDispatch`
- `ThermalMultiStart`
- `ThermalStandard`

## Storage
- `EnergyReservoirStorage`

## Electric Loads
- `ExponentialLoad`
- `FixedAdmittance`
- `InterruptiblePowerLoad`
- `InterruptibleStandardLoad`
- `MotorLoad`
- `PowerLoad`
- `ShiftablePowerLoad`
- `StandardLoad`
- `SwitchedAdmittance`

## Branches
- `AreaInterchange`
- `BranchesSeries`
- `DiscreteControlledACBranch`
- `DynamicBranch`
- `Line`
- `MonitoredLine`
- `TModelHVDCLine`
- `TwoTerminalGenericHVDCLine`
- `TwoTerminalLCCLine`
- `TwoTerminalVSCLine`

