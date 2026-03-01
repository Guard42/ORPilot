"""HuggingFace dataset loader for benchmark cases."""

from __future__ import annotations


def load_hf_cases(
    dataset: str,
    split: str = "test",
    difficulty: str | None = None,
    ids: list[int] | None = None,
    limit: int | None = None,
) -> list:
    """Load BenchmarkCase objects from a HuggingFace dataset.

    Parameters
    ----------
    dataset:
        HuggingFace dataset name, e.g. ``"CardinalOperations/IndustryOR"``.
    split:
        Dataset split to load (default ``"test"``).
    difficulty:
        Optional filter: ``"Easy"``, ``"Medium"``, or ``"Hard"`` (case-insensitive).
    ids:
        Optional list of row ``id`` values to include.
    limit:
        Maximum number of cases to return.

    Returns
    -------
    list[BenchmarkCase]
    """
    try:
        from datasets import load_dataset  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "The 'datasets' package is required for HuggingFace dataset loading. "
            "Install it with: pip install 'orpilot[hf]'  or  pip install datasets"
        ) from exc

    from orpilot.benchmark.case import BenchmarkCase

    hf_data = load_dataset(dataset, split=split)

    cases: list[BenchmarkCase] = []
    for row in hf_data:
        # Filter by ids
        if ids is not None and row["id"] not in ids:
            continue

        # Filter by difficulty (case-insensitive)
        if difficulty is not None and row["difficulty"].lower() != difficulty.lower():
            continue

        expected = float(row["en_answer"])
        tol = max(1e-4, abs(expected) * 1e-3)

        case = BenchmarkCase(
            name=f"industryOR_{row['id']:03d}",
            problem_text=row["en_question"],
            tables=None,
            ir_model=None,
            expected_objective=expected,
            objective_tolerance=tol,
            source=f"{dataset}/{split}",
            tags=[row["difficulty"].lower(), "industryOR"],
        )
        cases.append(case)

        if limit is not None and len(cases) >= limit:
            break

    return cases
