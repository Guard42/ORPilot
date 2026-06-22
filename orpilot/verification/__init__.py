"""OR-Copilot 4-Layer Verification Framework.

Synthesizes verification approaches from:
- MURKA: 4D composite reward (format, constraint, semantic, similarity)
- OR-LLM-Agent: 3-stage escalation protocol (code → model → strategy → human)
- AutoFormulator: SMT-based equivalence + dual reward (solver × LLM)
- CoE: Backward Reflection with blame attribution
- OR-CI: Metamorphic testing (cost_scaling, constraint_relaxation)
- NL2OR: AST-based error detection
"""

from orpilot.verification.verifier import (
    VerificationLayer,
    VerificationResult,
    LayerResult,
    Verifier,
    EscalationLevel,
    MURKAReward,
)

__all__ = [
    "VerificationLayer",
    "VerificationResult",
    "LayerResult",
    "Verifier",
    "EscalationLevel",
    "MURKAReward",
]
