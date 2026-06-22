# /orpilot:configure — Configure OR-Copilot Settings

## Description
Interactive configuration of solver backend, LLM architecture tier, model selection, and knowledge base settings.

## Usage
```
/orpilot:configure
```

## Configuration Options

### 1. Solver Backend
Which solver should be used (user must choose ONE):
- `gurobi`: Best for MILP, academic license available
- `cplex`: Alternative commercial solver
- `pulp` (CBC): Free, good for LP/small MILP
- `pyomo`: Flexible multi-backend
- `ortools`: Best for CP and combinatorial

### 2. LLM Architecture Tier
- `A — Single Model`: All tasks use same model (fastest, lowest cost)
- `B — Main + Sub-Agent Secondary`: Pipeline uses main model, sub-agents use Haiku/Sonnet
- `C — Full Tiered`: Claude Code native 4-tier (Opus/Sonnet/Haiku for different tasks)

### 3. Knowledge Bases
- Enable/disable domain-specific knowledge bases
- Configure KB directories

### 4. Output Settings
- `--generate-ir`: Always generate IR after solve
- `--save-data`: Save extracted data to output
- `--verbose`: Show solver logs by default

Settings are saved to `orpilot.toml`.
