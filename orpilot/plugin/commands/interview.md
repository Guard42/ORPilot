# /orpilot:interview — Interactive Problem Clarification

## Description
Start an interactive interview session to clarify and structure an optimization problem. Saves session state for later resumption or use with /orpilot:solve.

## Usage
```
/orpilot:interview
/orpilot:interview --session output/session.json
```

## Flow
1. Start conversational interview with the user
2. Ask targeted questions to understand: decisions, objectives, constraints, data
3. Resolve domain-specific terminology (CoE Terminology Interpreter pattern)
4. When complete, save session.json with structured problem understanding
5. User can resume later with `/orpilot:solve --session output/session.json`

## Flags
- `--session <path>`: Session file path (default: output/session.json)
- `--no-resume`: Always start fresh, ignore existing session

## Output
- `output/session.json`: Saved interview state
