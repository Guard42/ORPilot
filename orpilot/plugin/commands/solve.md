# /orpilot:solve — Full Optimization Problem Solver

## Description
Solve an optimization problem from natural language description. Runs the complete OR-Copilot pipeline: interview → classify → solver-fit → user confirm → extract → formulate → code → verify → solve → report.

## Usage
```
/orpilot:solve [problem text or file path]
```

## Pipeline Flow

1. **or-interviewer**: Clarify ambiguous details through targeted questioning
2. **or-classifier**: Define business problem and classify OR problem type
3. **or-solver-fit**: Analyze solver suitability, recommend technical approach
4. **⏸ User Confirmation**: Review and approve problem definition, classification, solver choice
5. **or-extractor**: Extract structured 5-tuple {Sets, Params, Vars, Constraints, Objective}
6. **└─ Hook: post_extraction_verify**: Auto-validate 5-tuple completeness
7. **or-formulator**: Build universal IR v2 with mathematical formulations
8. **or-coder**: Generate solver-specific executable code
9. **└─ Hook: post_code_gen_check**: Auto-validate syntax and executability
10. **or-verifier**: 4-layer verification with escalation protocol
11. **Solver Execution**: Run the solver, collect results
12. **or-reporter**: Generate human-readable solution report

## Flags
- `--architecture <A|B|C>`: LLM model architecture (default: B)
  - `A`: Single model for all tasks
  - `B`: Main model for pipeline, secondary for sub-agents
  - `C`: Full Claude Code tiered (Opus/Sonnet/Haiku)
- `--solver <gurobi|cplex|pulp|pyomo|ortools>`: Target solver backend (prompted if not specified)
- `--output-dir <path>`: Directory for output files (default: output/)
- `--data-dir <path>`: Directory for input CSV files (default: data/)
- `--generate-ir`: Generate ir.json after successful solve
- `--max-retries <n>`: Max code generation retry attempts (default: 3)
- `--time-limit <seconds>`: Solver time limit (default: 300)
- `--verbose`: Show full error details and solver logs
- `--session <path>`: Resume from saved session.json

## Examples
```
/orpilot:solve "I need to assign 5 workers to 3 tasks to minimize total cost"
/orpilot:solve problem.txt --solver gurobi --generate-ir
/orpilot:solve --session output/session.json --architecture C
```

## Output
- `output/model.py`: Generated solver code
- `output/solution_*.csv`: Solution variable values
- `output/optimization_summary.txt`: Status and objective value
- `output/ir.json`: Intermediate representation (if --generate-ir)
- `output/metrics.json`: Per-node token usage, latency, retry counts
- `output/session.json`: Pipeline state for resumption
