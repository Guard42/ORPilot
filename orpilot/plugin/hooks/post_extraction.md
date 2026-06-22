# post_extraction — Auto-Validate Structured Extraction Output

## Hook Type: PostToolUse
## Triggers After: or-extractor agent completes

## Purpose
Automatically validate the structured 5-tuple {Sets, Parameters, Variables, Constraints, Objective} extracted by `or-extractor` before handing off to `or-formulator`. Catch extraction errors early — they are the most expensive to fix downstream.

## Validation Checks

### 1. Completeness Check
- [ ] All 5 sections present (sets, parameters, variables, constraints, objective)
- [ ] At least one set defined
- [ ] At least one parameter defined (or explicit flag that problem has no data)
- [ ] At least one decision variable defined
- [ ] At least one constraint defined
- [ ] Objective defined with sense (minimize/maximize)

### 2. Cross-Referencing Check
- [ ] Every parameter referenced in constraints is defined in parameters section
- [ ] Every variable referenced in constraints is defined in variables section
- [ ] Every index symbol (i, j, t, ...) in expressions maps to a defined set
- [ ] No undefined references in the objective expression

### 3. Type Consistency Check
- [ ] Variable types (continuous/integer/binary) match their usage context
- [ ] Parameter types (float/integer) are consistent with their mathematical usage
- [ ] Constraint relations (<=, >=, ==) are appropriate for the constraint semantics

### 4. Semantic Coherence Check
- [ ] No contradictory constraints (e.g., x >= 5 AND x <= 3)
- [ ] Units are consistent (all costs in same currency, all times in same unit)
- [ ] Variable lower bounds <= upper bounds
- [ ] Extraction confidence scores are present and reasonable

## Action On Failure
If ANY check fails:
1. Report the specific failure with the failing element
2. Route back to `or-extractor` with the error context for correction
3. Set `needs_re_extraction: true` in the pipeline state

If ALL checks pass:
1. Report "Extraction validated — 5-tuple is complete and consistent"
2. Allow pipeline to proceed to `or-formulator`

## Output: ValidationReport with pass/fail status and specific failure details
