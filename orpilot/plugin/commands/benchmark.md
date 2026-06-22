# /orpilot:benchmark — Run OR Modeling Benchmarks

## Description
Run the OR-Copilot pipeline against standard benchmarks to evaluate modeling accuracy: IndustryOR (100 industrial problems), G-REAL (graph problems), BWOR (82 textbook problems), NL4OPT, MAMO.

## Usage
```
/orpilot:benchmark industryor
/orpilot:benchmark greal --difficulty Easy --limit 10
```

## Supported Benchmarks
- `industryor`: 100 real-world OR problems from 13 industries
- `greal`: 3600 graph problem instances (TSP, coloring, vertex cover, shortest path)
- `bwor`: 82 problems from standard OR textbooks
- `nl4opt`: Natural language optimization benchmark
- `mamo`: Mixed-integer optimization benchmark (Easy + Complex)

## Flags
- `--difficulty <Easy|Medium|Hard>`: Filter by difficulty
- `--limit <n>`: Cap the number of problems to run
- `--architecture <A|B|C>`: LLM model architecture
- `--output-dir <path>`: Results directory

## Output
- Results per problem with pass/fail status
- Aggregate accuracy metrics (pass@1, pass@8, mj@8)
- Comparison against published baselines
