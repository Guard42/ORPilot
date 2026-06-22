"""Problem Understanding Cluster — 5-Step Fixed Pipeline.

Fixed flow (not configurable — no branching strategies):
  1. Interview Agent (or-interviewer) — clarify ambiguous business details
  2. Define & Classify Agent (or-classifier) — problem definition + OR type
  3. Solver Fit Agent (or-solver-fit) — solver suitability + technical route
  4. User Confirmation — present analysis, wait for user approval
  5. Structured Extraction (or-extractor) — 5-tuple extraction

Design Motivation:
  - Classification and solver-fit used to be configurable strategies;
    they are now DEFAULT pipeline steps (per user instruction).
  - Data Spec Agent removed to keep the cluster clean.
  - Every step before extraction MUST be user-confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Pipeline State
# ---------------------------------------------------------------------------

class ClusterPhase(str, Enum):
    """Phases of the Problem Understanding Cluster."""
    INTERVIEW = "interview"
    CLASSIFY = "classify"
    SOLVER_FIT = "solver_fit"
    CONFIRM = "confirm"
    EXTRACT = "extract"
    DONE = "done"


@dataclass
class ProblemUnderstandingState:
    """State carried through the Problem Understanding Cluster."""
    # Raw input
    raw_description: str = ""

    # Interview outputs
    problem_summary: str = ""
    key_decisions: list[str] = field(default_factory=list)
    objective_statement: str = ""
    core_constraints: list[str] = field(default_factory=list)
    domain_terms: dict[str, str] = field(default_factory=dict)

    # Classification outputs
    problem_definition: str = ""
    primary_type: str = ""
    math_type: str = ""
    scale: str = ""
    industry_domain: str = ""

    # Solver fit outputs
    solver_suitable_parts: list[dict] = field(default_factory=list)
    non_solver_parts: list[dict] = field(default_factory=list)
    solver_options: list[dict] = field(default_factory=list)
    recommended_route: str = ""

    # User confirmations
    interview_confirmed: bool = False
    classification_confirmed: bool = False
    solver_fit_confirmed: bool = False

    # Extraction output
    extracted_elements: dict | None = None

    # Phase tracking
    current_phase: ClusterPhase = ClusterPhase.INTERVIEW
    user_needs_to_confirm: bool = False
    confirmation_summary: str = ""


# ---------------------------------------------------------------------------
# Confirmation Messages
# ---------------------------------------------------------------------------

def build_interview_confirmation(state: ProblemUnderstandingState) -> str:
    """Build the confirmation message after interview."""
    return f"""## Problem Understanding Confirmation

**Summary**: {state.problem_summary}

**Key Decisions**:
{chr(10).join(f'- {d}' for d in state.key_decisions)}

**Objective**: {state.objective_statement}

**Core Constraints**:
{chr(10).join(f'- {c}' for c in state.core_constraints)}

**Domain Terms Resolved**: {state.domain_terms if state.domain_terms else 'None'}

Is this understanding correct? Type **yes** to proceed or provide corrections."""


def build_classification_confirmation(state: ProblemUnderstandingState) -> str:
    """Build the confirmation message after classification."""
    return f"""## Problem Classification Confirmation

**Problem Definition**: {state.problem_definition}

**Primary Type**: {state.primary_type}
**Math Type**: {state.math_type}
**Scale**: {state.scale}
**Industry Domain**: {state.industry_domain}

Is this classification correct? Type **yes** to proceed or provide corrections."""


def build_solver_fit_confirmation(state: ProblemUnderstandingState) -> str:
    """Build the confirmation message after solver fit analysis."""
    lines = ["## Solver Fit Analysis Confirmation", ""]

    if state.solver_suitable_parts:
        lines.append("**Solver-Suitable Parts**:")
        for part in state.solver_suitable_parts:
            lines.append(f"- {part.get('component', '?')}: {part.get('formulation_type', '?')} "
                        f"(~{part.get('estimated_variables', '?')} vars, "
                        f"~{part.get('estimated_constraints', '?')} constraints)")

    if state.non_solver_parts:
        lines.append("")
        lines.append("**Non-Solver Parts**:")
        for part in state.non_solver_parts:
            lines.append(f"- {part.get('component', '?')}: {part.get('recommended_approach', '?')} "
                        f"({part.get('rationale', '?')})")

    lines.append("")
    lines.append("**Solver Options**:")
    for opt in state.solver_options:
        suitability = opt.get('suitability', '?')
        lines.append(f"- **{opt.get('name', '?')}**: {suitability} — {opt.get('rationale', '?')}")

    lines.append("")
    lines.append(f"**Recommended Route**: {state.recommended_route}")
    lines.append("")
    lines.append("Which solver would you like to use? (gurobi / cplex / pulp / pyomo / ortools)")
    lines.append("Type your choice to proceed, or provide corrections.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

class ProblemUnderstandingPipeline:
    """Orchestrates the 5-step fixed pipeline for problem understanding.

    This is the DEFAULT pipeline — no configurable strategies.
    After user confirmation at each checkpoint, the pipeline advances.
    """

    def __init__(self):
        self.state = ProblemUnderstandingState()

    # ------------------------------------------------------------------
    # Step 1: Interview
    # ------------------------------------------------------------------

    def start_interview(self, raw_description: str) -> str:
        """Begin the interview phase."""
        self.state.raw_description = raw_description
        self.state.current_phase = ClusterPhase.INTERVIEW
        return (
            "I'll help you structure your optimization problem. "
            "Let me ask a few clarifying questions."
        )

    def ingest_interview_output(self, output: dict) -> str:
        """Ingest the or-interviewer agent's structured output."""
        self.state.problem_summary = output.get("problem_summary", "")
        self.state.key_decisions = output.get("key_decisions", [])
        self.state.objective_statement = output.get("objective", "")
        self.state.core_constraints = output.get("core_constraints", [])
        self.state.domain_terms = output.get("domain_terms_resolved", {})
        self.state.current_phase = ClusterPhase.CONFIRM
        self.state.user_needs_to_confirm = True
        self.state.confirmation_summary = build_interview_confirmation(self.state)
        return self.state.confirmation_summary

    # ------------------------------------------------------------------
    # Step 2: Classification
    # ------------------------------------------------------------------

    def start_classification(self) -> None:
        """Advance to classification phase."""
        self.state.interview_confirmed = True
        self.state.current_phase = ClusterPhase.CLASSIFY
        self.state.user_needs_to_confirm = False

    def ingest_classification_output(self, output: dict) -> str:
        """Ingest the or-classifier agent's output."""
        self.state.problem_definition = output.get("problem_definition", "")
        self.state.primary_type = output.get("primary_type", "")
        self.state.math_type = output.get("math_type", "")
        self.state.scale = output.get("scale", "")
        self.state.industry_domain = output.get("industry_domain", "")
        self.state.current_phase = ClusterPhase.CONFIRM
        self.state.user_needs_to_confirm = True
        self.state.confirmation_summary = build_classification_confirmation(self.state)
        return self.state.confirmation_summary

    # ------------------------------------------------------------------
    # Step 3: Solver Fit
    # ------------------------------------------------------------------

    def start_solver_fit(self) -> None:
        """Advance to solver fit analysis phase."""
        self.state.classification_confirmed = True
        self.state.current_phase = ClusterPhase.SOLVER_FIT
        self.state.user_needs_to_confirm = False

    def ingest_solver_fit_output(self, output: dict) -> str:
        """Ingest the or-solver-fit agent's output."""
        self.state.solver_suitable_parts = output.get("solver_suitable_parts", [])
        self.state.non_solver_parts = output.get("non_solver_parts", [])
        self.state.solver_options = output.get("solver_options", [])
        self.state.recommended_route = output.get("recommended_route", "")
        self.state.current_phase = ClusterPhase.CONFIRM
        self.state.user_needs_to_confirm = True
        self.state.confirmation_summary = build_solver_fit_confirmation(self.state)
        return self.state.confirmation_summary

    # ------------------------------------------------------------------
    # Step 4: User Confirmation
    # ------------------------------------------------------------------

    def process_user_response(self, response: str) -> tuple[bool, str]:
        """Process user confirmation response.

        Returns (should_proceed, message).
        """
        response_lower = response.strip().lower()

        # Solver selection during solver_fit confirm
        if (self.state.current_phase == ClusterPhase.CONFIRM and
            not self.state.solver_fit_confirmed):
            valid_solvers = {"gurobi", "cplex", "pulp", "pyomo", "ortools"}
            if response_lower in valid_solvers:
                self.state.solver_fit_confirmed = True
                self.state.user_needs_to_confirm = False
                return True, f"Solver set to **{response_lower}**. Proceeding to extraction."

        # General yes/no
        if response_lower in ("yes", "y", "proceed"):
            if not self.state.interview_confirmed:
                self.state.interview_confirmed = True
                return True, "Proceeding to problem classification."
            elif not self.state.classification_confirmed:
                self.state.classification_confirmed = True
                return True, "Proceeding to solver fit analysis."
            elif not self.state.solver_fit_confirmed:
                self.state.solver_fit_confirmed = True
                return True, "Proceeding to structured extraction."

        if response_lower in ("no", "n", "revise"):
            return False, "What would you like to revise?"

        return False, response  # Pass through for specific corrections

    # ------------------------------------------------------------------
    # Step 5: Extraction
    # ------------------------------------------------------------------

    def start_extraction(self) -> dict:
        """Build the extraction context for or-extractor agent."""
        return {
            "problem_summary": self.state.problem_summary,
            "problem_definition": self.state.problem_definition,
            "primary_type": self.state.primary_type,
            "math_type": self.state.math_type,
            "objective": self.state.objective_statement,
            "constraints": self.state.core_constraints,
            "key_decisions": self.state.key_decisions,
            "raw_description": self.state.raw_description,
        }

    def ingest_extraction_output(self, output: dict) -> None:
        """Ingest the or-extractor agent's 5-tuple output."""
        self.state.extracted_elements = output
        self.state.current_phase = ClusterPhase.DONE

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self.state.current_phase == ClusterPhase.DONE

    @property
    def needs_user_input(self) -> bool:
        return self.state.user_needs_to_confirm

    def get_confirmation_prompt(self) -> str:
        """Get the current confirmation prompt for the user."""
        return self.state.confirmation_summary
