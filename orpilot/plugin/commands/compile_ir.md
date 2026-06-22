# /orpilot:compile-ir — Compile IR to Solver Code (No LLM)

## Description
Compile an IR JSON file to executable solver code. This is fully deterministic — no LLM calls, zero cost beyond solver execution. Useful for re-running solutions with different data or solvers.

## Usage
```
/orpilot:compile-ir output/ir.json
/orpilot:compile-ir output/ --solver pulp --run
```

## Flags
- `--solver <gurobi|cplex|pulp|pyomo|ortools>`: Target solver (default: from config)
- `--out <path>`: Output path for model.py (default: model.py next to ir.json)
- `--data-dir <path>`: Directory with CSV data files
- `--run`: Execute the compiled model after generation
- `--solver-log / --no-solver-log`: Stream solver output
- `--time-limit <seconds>`: Solver time limit

## Examples
```
/orpilot:compile-ir output/ir.json --solver gurobi --run
/orpilot:compile-ir output/ --solver pulp --data-dir data/ --run
```

## Output
- `model.py`: Compiled solver code
- Solution CSV files (if --run)
