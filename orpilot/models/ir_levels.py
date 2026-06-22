"""Multi-Level IR (MLIR / Rust HIR→MIR pattern) for progressive lowering.

HIR (High-Level IR): LLM-friendly, contains natural language, semantic roles.
MIR (Mid-Level IR): Solver-agnostic, mathematically precise, no NL.
LIR (Low-Level IR): Solver-specific, contains concrete API calls.

Inspired by:
- MLIR: https://mlir.llvm.org/
- Rust HIR: https://rustc-dev-guide.rust-lang.org/hir.html
- Rust MIR: https://rustc-dev-guide.rust-lang.org/mir/index.html
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class HIRModel:
    """High-Level IR — what LLMs generate.

    Contains natural language descriptions, semantic role labels,
    domain annotations, and "derived_from" text excerpts.
    Purpose: LLM generation target, human readability.
    """
    schema_version: str = "hir-1.0"
    problem_class: str = ""
    problem_type: str = ""
    sense: str = "minimize"
    description: str = ""

    sets: dict[str, dict] = field(default_factory=dict)
    parameters: dict[str, dict] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)
    constraints: dict[str, dict] = field(default_factory=dict)
    objective: dict = field(default_factory=dict)

    # HIR-specific: LLM-friendly metadata
    metadata: dict = field(default_factory=dict)
    domain_annotations: dict[str, Any] = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def lower_to_mir(self) -> MIRModel:
        """Deterministic HIR→MIR lowering.

        Strips natural language, resolves set members, normalizes structure.
        """
        return MIRModel(
            problem_class=self.problem_class,
            problem_type=self.problem_type,
            sense=self.sense,
            sets=_resolve_sets(self.sets),
            parameters=_resolve_parameters(self.parameters, self.sets),
            variables=_resolve_variables(self.variables),
            constraints=self.constraints,
            objective=self.objective,
        )


@dataclass
class MIRModel:
    """Mid-Level IR — solver-agnostic, mathematically precise.

    All sets have resolved members. All parameters have types and defaults.
    No natural language. No solver-specific details.

    Purpose: cross-solver portability, optimization pass target.
    """
    problem_class: str = ""
    problem_type: str = ""
    sense: str = "minimize"

    sets: dict[str, dict] = field(default_factory=dict)
    parameters: dict[str, dict] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)
    constraints: dict[str, dict] = field(default_factory=dict)
    objective: dict = field(default_factory=dict)


@dataclass
class LIRModel:
    """Low-Level IR — solver-specific.

    Contains concrete solver API calls, variable declarations,
    constraint construction code, and solver-specific annotations.

    Purpose: code generation target for a specific solver backend.
    """
    solver_name: str = ""
    imports: list[str] = field(default_factory=list)
    model_setup: list[str] = field(default_factory=list)
    variable_declarations: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    objective: str = ""
    solve_block: list[str] = field(default_factory=list)
    extraction: list[str] = field(default_factory=list)

    def emit(self) -> str:
        """Emit complete Python source code."""
        parts = []
        parts.extend(self.imports)
        parts.append("")
        parts.append("def solve(data, time_limit=None, show_solver_log=False):")
        parts.extend(f"    {line}" for line in self.model_setup)
        parts.append("")
        parts.extend(f"    {line}" for line in self.variable_declarations)
        parts.append("")
        parts.extend(f"    {line}" for line in self.constraints)
        parts.append(f"    {self.objective}")
        parts.extend(f"    {line}" for line in self.solve_block)
        parts.append("")
        parts.extend(f"    {line}" for line in self.extraction)
        return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Lowering helpers
# ---------------------------------------------------------------------------

def _resolve_sets(sets: dict) -> dict:
    """Resolve set members: expand range-based sets, validate CSV-based sets."""
    resolved = {}
    for name, meta in sets.items():
        resolved[name] = dict(meta)
        if "members" in meta and meta["members"]:
            continue  # Already resolved
        if "size" in meta and meta["size"] is not None:
            resolved[name]["members"] = list(range(meta["size"]))
    return resolved


def _resolve_parameters(params: dict, sets: dict) -> dict:
    """Add missing_default='zero' for any parameter without it."""
    resolved = {}
    for name, meta in params.items():
        resolved[name] = dict(meta)
        if "missing_default" not in meta:
            resolved[name]["missing_default"] = "zero"
    return resolved


def _resolve_variables(vars_: dict) -> dict:
    """Add lower_bound=0.0 for continuous vars without explicit bound."""
    resolved = {}
    for name, meta in vars_.items():
        resolved[name] = dict(meta)
        if meta.get("type", "continuous") != "binary" and "lower_bound" not in meta:
            resolved[name]["lower_bound"] = 0.0
    return resolved
