# Job Assignment Problem

Assign workers to tasks (one-to-one) to minimize total cost. Each task must be assigned exactly one worker; each worker handles at most one task.

## Problem

- **Decision variable:** `assign[w, t]` — binary, 1 if worker `w` is assigned to task `t`
- **Objective:** Minimize Σ cost[w,t] × assign[w,t]
- **Constraints:**
  - Each task gets exactly one worker: Σ_w assign[w,t] = 1
  - Each worker handles at most one task: Σ_t assign[w,t] ≤ 1

Note: worker IDs and task IDs intentionally contain underscores to validate that the `\x1f` key separator is used correctly.

## Data

| File | Description |
|------|-------------|
| `data/workers.csv` | Worker IDs |
| `data/tasks.csv` | Task IDs |
| `data/costs.csv` | Cost of assigning each worker to each task |

### workers.csv
| worker_id |
|---|
| alice |
| bob |
| carol |

### tasks.csv
| task_id |
|---|
| task_1 |
| task_2 |
| task_3 |

### costs.csv (worker × task cost matrix)
|  | task_1 | task_2 | task_3 |
|---|---|---|---|
| alice | 4 | 8 | 7 |
| bob | 5 | 3 | 6 |
| carol | 6 | 4 | 5 |

## Expected Optimal Solution

**Objective value: 12**

| Assignment | Cost |
|---|---|
| alice → task_1 | 4 |
| bob → task_2 | 3 |
| carol → task_3 | 5 |
| **Total** | **12** |
