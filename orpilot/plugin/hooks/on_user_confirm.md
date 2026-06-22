# on_user_confirm — Intercept User Confirmation During Pipeline Phases

## Hook Type: UserPromptSubmit
## Triggers: When pipeline is in confirmation mode during problem definition / classification / solver-fit phases

## Purpose
Ensure that the user explicitly confirms the problem definition, OR classification, solver suitability analysis, and solving route BEFORE the pipeline proceeds to expensive structured extraction and formulation. This prevents wasted LLM calls on incorrectly understood problems.

## When This Hook Activates

This hook activates when the pipeline state contains `requires_user_confirmation: true`, which is set after:
1. `or-interviewer` completes — user confirms problem understanding
2. `or-classifier` completes — user confirms problem type classification
3. `or-solver-fit` completes — user confirms which solver to use and which approach to take

## User Confirmation Flow

### Step 1: Present Analysis Summary
When a confirmation point is reached, present the user with a clear summary:
```markdown
## 📋 Pipeline Checkpoint: [Phase Name]

**[Phase Agent]** has produced the following analysis:

[Structured summary of what was produced]

### 🔍 Please confirm:
1. Is the [problem definition / classification / solver choice] correct?
2. Would you like to make any changes before proceeding?

**Type 'yes' to proceed, 'no' to revise, or provide specific corrections.**
```

### Step 2: Process User Response
- **"yes" / "y" / "proceed"**: Confirm and advance to next pipeline phase
- **"no" / "n"**: Return to the previous agent for revision
- **Specific correction**: Feed the user's correction back to the agent and re-run that phase
- **"quit" / "exit"**: Abort the pipeline, save current state

### Step 3: State Management
After confirmation:
- Set `requires_user_confirmation: false`
- Set `confirmed_{phase}: true` in the pipeline state
- Log the user's confirmation decision
- Proceed to the next agent

## Confirmation Points in the Pipeline

| Phase | Agent | What is Confirmed |
|---|---|---|
| 1 | or-interviewer | Problem understanding is complete and correct |
| 2 | or-classifier | Problem type classification is accurate |
| 3 | or-solver-fit | Solver choice and technical approach are approved |

After all 3 confirmations, the pipeline proceeds to `or-extractor` without further user interaction (fully automated extraction → formulation → code → verify → solve → report).

## Design Rationale
Inspired by OR-LLM-Agent's clarification pipeline and Chain-of-Experts' backward reflection: getting user confirmation at the RIGHT points prevents cascading errors. The key insight is that extraction/formulation errors are MUCH more expensive to fix than classification errors — catching classification errors early saves significant downstream LLM cost.

**Inspired by**: OR-LLM-Agent clarification pipeline, CoE Backward Reflection error localization, OptiMUS interactive quality checks
