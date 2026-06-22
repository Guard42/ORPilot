"""Pydantic models for the Intermediate Representation (IR) v2 of an OR model.

Synthesizes IR designs from 11 papers:
- OptiMUS: Connection Graph, Optimization Techniques
- Chain-of-Experts: Problem classification metadata
- NL2OR: Structured 5-tuple with data contracts
- AutoFormulator: Equivalent formulation tracking, dual reward support
- MURKA: Extraction confidence scoring
- MA-GTS: Domain-specific annotations
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProblemClass(str, Enum):
    TRANSPORTATION = "transportation"
    SCHEDULING = "scheduling"
    ASSIGNMENT = "assignment"
    PRODUCTION_PLANNING = "production_planning"
    FACILITY_LOCATION = "facility_location"
    INVENTORY = "inventory"
    ROUTING = "routing"
    PORTFOLIO = "portfolio"
    GRAPH = "graph"
    KNAPSACK = "knapsack"
    OTHER = "other"


class MathType(str, Enum):
    LP = "LP"
    MILP = "MILP"
    MINLP = "MINLP"
    CP = "CP"
    QP = "QP"
    MIQP = "MIQP"
    COMBINATORIAL = "combinatorial"
    GRAPH_THEORETIC = "graph_theoretic"
    NONLINEAR = "nonlinear"


class LinearityType(str, Enum):
    LINEAR = "linear"
    QUADRATIC = "quadratic"
    GENERAL_NONLINEAR = "general_nonlinear"
    CONVEX = "convex"
    NONCONVEX = "nonconvex"
    LOGICAL = "logical"


class OptimizationTechniqueType(str, Enum):
    SOS1 = "sos1"
    SOS2 = "sos2"
    INDICATOR = "indicator"
    BIG_M = "big_m"
    LINEARIZATION = "linearization"
    SYMMETRY_BREAKING = "symmetry_breaking"
    WARM_START = "warm_start"


# ---------------------------------------------------------------------------
# V2 Extended Models
# ---------------------------------------------------------------------------

class IRMetadata(BaseModel):
    """Traceability and audit metadata."""
    generated_by: str = "or-copilot-v2"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    assumptions: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    problem_description_hash: str | None = None


class IRProvenance(BaseModel):
    """Extraction and formulation provenance for quality tracking."""
    extractor_version: str | None = None
    formulator_version: str | None = None
    extraction_confidence: dict[str, float] = Field(default_factory=dict)
    verification_checks_passed: int = 0
    verification_checks_failed: int = 0
    llm_model_used: str | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class ConnectionGraph(BaseModel):
    """OptiMUS-inspired dependency tracking.

    Enables context-window management: when debugging a specific
    constraint, only related variables/parameters are shown.
    """
    parameter_to_clauses: dict[str, list[str]] = Field(default_factory=dict)
    variable_to_clauses: dict[str, list[str]] = Field(default_factory=dict)
    clause_dependencies: dict[str, list[str]] = Field(default_factory=dict)


class OptimizationTechnique(BaseModel):
    """OptiMUS-inspired: captures solver-specific structure annotations."""
    technique: OptimizationTechniqueType
    target: str  # Variable or constraint name
    parameters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# V1 Models (extended with V2 fields)
# ---------------------------------------------------------------------------

class IRSet(BaseModel):
    size: int | None = None
    index_symbol: str
    source: str | None = None
    column: str | None = None
    size_source: str | None = None
    size_column: str | None = None
    ordered: bool = False
    # V2 additions
    members: list[Any] | None = None  # NL2OR: explicit member list
    domain_type: str | None = None    # discrete, continuous, temporal, categorical


class IRParameter(BaseModel):
    domain: list[str]
    type: str
    source: str | None = None
    column: str | None = None
    index_columns: list[str] | None = None
    missing_default: str = "zero"
    optional: bool = False
    # V2 additions
    description: str | None = None    # Human-readable description
    unit: str | None = None           # Physical unit (e.g., "USD", "kg", "hours")
    default_value: Any = None         # Default when data is missing


class IRVariable(BaseModel):
    description: str
    label: str | None = None
    domain: list[str]
    type: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    upper_bound_set: str | None = None
    exclude_diagonal: bool = False
    # V2 additions
    semantic_role: str | None = None  # flow, inventory, assignment, production, selection
    sos_weights: list[float] | None = None  # OptiMUS: for SOS variables
    indicator_trigger: str | None = None    # OptiMUS: for indicator variables


class IRConstraint(BaseModel):
    domain: list[str]
    expression: dict[str, Any]
    sense: str
    rhs: dict[str, Any]
    # V2 additions
    name: str | None = None           # Named constraint for debugging
    type: LinearityType = LinearityType.LINEAR
    technique: str | None = None      # big_m, indicator, sos, linearization
    description: str | None = None    # Natural language description
    derived_from: str | None = None   # Original problem text excerpt
    connection_graph_id: str | None = None  # OptiMUS CG reference


class IRObjective(BaseModel):
    sense: str
    expression: dict[str, Any]
    # V2 addition
    description: str | None = None    # Natural language description


# ---------------------------------------------------------------------------
# V2 IR Model (backward compatible with V1)
# ---------------------------------------------------------------------------

class IRModel(BaseModel):
    """Universal IR v2 — combines all V1 fields with V2 extensions."""
    # V1 core fields (maintained for backward compatibility)
    problem_class: str
    model_type: str
    sense: str
    sets: dict[str, IRSet]
    parameters: dict[str, IRParameter]
    variables: dict[str, IRVariable]
    constraints: dict[str, IRConstraint]
    objective: IRObjective

    # V2 metadata
    schema_version: str = "2.0"
    metadata: IRMetadata = Field(default_factory=IRMetadata)
    problem_type: MathType = MathType.MILP  # Mathematical problem type

    # V2 structural
    connection_graph: ConnectionGraph = Field(default_factory=ConnectionGraph)
    optimization_techniques: list[OptimizationTechnique] = Field(default_factory=list)

    # V2 annotations
    linearity_annotations: dict[str, LinearityType] = Field(default_factory=dict)
    domain_annotations: dict[str, Any] = Field(default_factory=dict)
    equivalent_formulations: list[str] = Field(default_factory=list)

    # V2 provenance
    provenance: IRProvenance = Field(default_factory=IRProvenance)
