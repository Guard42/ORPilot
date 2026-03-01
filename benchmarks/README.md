# ORPilot Benchmarks

Benchmark cases for testing the ORPilot pipeline against known-optimal solutions.

## Directory structure

```
benchmarks/
  <collection>/
    <NNN>_<name>/
      problem.txt    ← plain-text problem description (NLP4LP-style)
      expected.json  ← {"objective", "status", "tolerance", "source", "tags"}
      ir.json        ← reference IR (optional — enables Mode C / compiler-only)
      data/
        *.csv        ← pre-extracted tables (optional — enables Mode B / ir-builder)
```

## Test modes

| Mode | Artifacts required | LLM calls | CLI flag |
|------|--------------------|-----------|----------|
| C — compiler only | `ir.json` + `data/` | 0 | `--mode compiler` |
| B — IR builder    | `data/` | 1 | `--mode ir` |
| A — full pipeline | none | 2 | `--mode full` |

## Running benchmarks

```bash
# Compiler-only (no API key needed)
pytest tests/benchmark/test_compiler_only.py -m benchmark -v

# Single case via CLI
orpilot benchmark benchmarks/nlp4lp/001_transportation --mode compiler --solver pulp

# Full pipeline
orpilot benchmark benchmarks/nlp4lp/001_transportation --mode full --provider anthropic
```

## Collections

### nlp4lp

Problems drawn from the NLP4LP benchmark suite (or inspired by it).  Each
problem description is a self-contained paragraph that embeds all data values.

| # | Name | Type | Optimal |
|---|------|------|---------|
| 001 | transportation | LP | 280.0 |
| 002 | knapsack | IP | 35.0 |
