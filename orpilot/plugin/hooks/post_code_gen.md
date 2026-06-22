# post_code_gen — Auto-Validate Generated Solver Code

## Hook Type: PostToolUse
## Triggers After: or-coder agent completes

## Purpose
Automatically validate the generated solver code for syntax correctness and basic executability before handing off to `or-verifier` for full verification. This is a lightweight pre-check — `or-verifier` does the deep verification.

## Validation Checks

### 1. Syntax Check (AST Parse)
```python
import ast
try:
    ast.parse(generated_code)
    syntax_ok = True
except SyntaxError as e:
    syntax_ok = False
    error_detail = str(e)
```

### 2. Import Check
- [ ] All required solver libraries are importable (gurobipy, pulp, ortools, etc.)
- [ ] No imports of non-existent modules

### 3. Contract Check
- [ ] Code exports a `solve(data, time_limit=None, show_solver_log=False)` function
- [ ] Function signature is correct
- [ ] Function is at module level (not nested)

### 4. Quick Sandbox Execution (with trivial data)
- [ ] Code can be loaded as a Python module without errors
- [ ] The `solve` function is callable
- [ ] (Optional) Run with a minimal test dataset

### 5. Solver API Usage Check
- [ ] Solver-specific API calls are correct for the target solver
- [ ] No mixing of different solver APIs in the same script

## Action On Failure
If ANY check fails:
1. Capture the specific error (syntax error with line number, missing import, etc.)
2. Route back to `or-coder` with the error context for repair
3. Set `needs_code_repair: true` in the pipeline state
4. Increment the code repair attempt counter (max 3 before escalation)

If ALL checks pass:
1. Report "Code generated successfully — syntax and imports validated"
2. Allow pipeline to proceed to `or-verifier` for deep verification

## ORLM-Inspired Sandbox Execution
Following ORLM's execution-based evaluation pattern:
- Code is extracted from markdown block
- Written to a temporary file
- Executed via subprocess with timeout
- Output is captured and parsed

**Inspired by**: ORLM execution-based evaluation, OR-LLM-Agent code repair loop, NL2OR AST-based validation
