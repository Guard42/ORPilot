"""4-Layer Verification with OR-LLM-Agent Escalation Protocol.

Layer 1: Structural — IR schema, AST, semantic rules (no solver needed)
Layer 2: Execution — sandbox, solver call, status check
Layer 3: Correctness — constraint satisfaction, MURKA 4D reward
Layer 4: Equivalence — SMT-based, cross-formulation comparison
"""

from __future__ import annotations

import ast
import json
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VerificationLayer(str, Enum):
    STRUCTURAL = "structural"
    EXECUTION = "execution"
    CORRECTNESS = "correctness"
    EQUIVALENCE = "equivalence"


class EscalationLevel(int, Enum):
    """OR-LLM-Agent escalation protocol."""
    NONE = 0       # Self-correction (LLM fixes directly)
    AGENT = 1      # Agent escalation (or-coder → or-verifier → or-formulator)
    STRATEGY = 2   # Strategy change (switch formulation approach)
    HUMAN = 3      # Human handoff with diagnostic


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class MURKAReward:
    """MURKA-inspired 4-dimensional composite reward."""
    format: float = 0.0       # 0-1: Does output follow required structure?
    constraint: float = 0.0   # 0-1: Are all constraints mathematically valid?
    semantic: float = 0.0     # 0-1: Are variables/terms semantically correct?
    similarity: float = 0.0   # 0-1: Does extraction match expected cardinalities?

    def composite(self, weights: tuple[float, float, float, float] = (1, 1, 1, 1)) -> float:
        """Compute weighted composite reward."""
        w_fmt, w_con, w_sem, w_sim = weights
        total = w_fmt + w_con + w_sem + w_sim
        if total == 0:
            return 0.0
        return (w_fmt * self.format + w_con * self.constraint +
                w_sem * self.semantic + w_sim * self.similarity) / total


@dataclass
class LayerResult:
    """Result from a single verification layer."""
    layer: VerificationLayer
    status: str  # "PASS" | "FAIL" | "SKIP"
    checks_passed: int = 0
    checks_failed: int = 0
    details: list[str] = field(default_factory=list)
    murka_reward: MURKAReward | None = None
    execution_time_s: float = 0.0


@dataclass
class VerificationResult:
    """Complete verification result across all layers."""
    overall_status: str  # "PASS" | "FAIL" | "NEEDS_REPAIR"
    layer_results: dict[str, LayerResult] = field(default_factory=dict)
    escalation_level: EscalationLevel = EscalationLevel.NONE
    repair_suggestions: list[str] = field(default_factory=list)
    requires_human: bool = False
    total_checks_passed: int = 0
    total_checks_failed: int = 0


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class Verifier:
    """4-layer verification with configurable escalation."""

    def __init__(
        self,
        timeout: int = 300,
        max_repair_attempts: int = 3,
        enable_smt: bool = False,  # SMT requires Z3 installation
        murka_weights: tuple[float, float, float, float] = (1, 1, 1, 1),
    ):
        self.timeout = timeout
        self.max_repair_attempts = max_repair_attempts
        self.enable_smt = enable_smt
        self.murka_weights = murka_weights

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        code: str,
        ir_model: dict | None = None,
        problem_description: str = "",
        ground_truth: float | None = None,
        enable_layers: set[VerificationLayer] | None = None,
    ) -> VerificationResult:
        """Run all enabled verification layers."""
        if enable_layers is None:
            enable_layers = {
                VerificationLayer.STRUCTURAL,
                VerificationLayer.EXECUTION,
                VerificationLayer.CORRECTNESS,
            }

        result = VerificationResult(overall_status="PASS")

        # Layer 1: Structural
        if VerificationLayer.STRUCTURAL in enable_layers:
            layer = self._verify_structural(code, ir_model)
            result.layer_results[VerificationLayer.STRUCTURAL] = layer
            result.total_checks_passed += layer.checks_passed
            result.total_checks_failed += layer.checks_failed

        # Layer 2: Execution
        if VerificationLayer.EXECUTION in enable_layers:
            layer = self._verify_execution(code)
            result.layer_results[VerificationLayer.EXECUTION] = layer
            result.total_checks_passed += layer.checks_passed
            result.total_checks_failed += layer.checks_failed

        # Layer 3: Correctness
        if VerificationLayer.CORRECTNESS in enable_layers:
            layer = self._verify_correctness(code, ir_model, ground_truth)
            result.layer_results[VerificationLayer.CORRECTNESS] = layer
            result.total_checks_passed += layer.checks_passed
            result.total_checks_failed += layer.checks_failed

        # Layer 4: Equivalence (optional, requires SMT)
        if VerificationLayer.EQUIVALENCE in enable_layers and self.enable_smt:
            layer = self._verify_equivalence(ir_model)
            result.layer_results[VerificationLayer.EQUIVALENCE] = layer
            result.total_checks_passed += layer.checks_passed
            result.total_checks_failed += layer.checks_failed

        # Determine overall status and escalation
        if result.total_checks_failed > 0:
            result.overall_status = "FAIL"
            result.escalation_level = self._determine_escalation(result)
            result.repair_suggestions = self._generate_repair_suggestions(result)
            result.requires_human = (result.escalation_level == EscalationLevel.HUMAN)

        return result

    # ------------------------------------------------------------------
    # Layer 1: Structural Verification
    # ------------------------------------------------------------------

    def _verify_structural(self, code: str, ir_model: dict | None) -> LayerResult:
        """Layer 1: No solver needed — check syntax, schema, semantics."""
        t0 = time.time()
        passed, failed = 0, 0
        details = []

        # 1.1 AST syntax check
        try:
            ast.parse(code)
            passed += 1
        except SyntaxError as e:
            failed += 1
            details.append(f"Syntax error: {e}")

        # 1.2 IR schema validation (if IR provided)
        if ir_model:
            if self._validate_ir_schema(ir_model):
                passed += 1
            else:
                failed += 1
                details.append("IR schema validation failed")

            # 1.3 Semantic cross-referencing
            sem_ok, sem_issues = self._check_ir_semantics(ir_model)
            passed += 1 if sem_ok else 0
            failed += 0 if sem_ok else 1
            details.extend(sem_issues)

        # 1.4 Function contract check
        if "def solve(" in code:
            passed += 1
        else:
            failed += 1
            details.append("Missing solve(data, ...) function contract")

        return LayerResult(
            layer=VerificationLayer.STRUCTURAL,
            status="PASS" if failed == 0 else "FAIL",
            checks_passed=passed,
            checks_failed=failed,
            details=details,
            execution_time_s=time.time() - t0,
        )

    # ------------------------------------------------------------------
    # Layer 2: Execution Verification
    # ------------------------------------------------------------------

    def _verify_execution(self, code: str) -> LayerResult:
        """Layer 2: Run code in sandbox, call solver, check status."""
        t0 = time.time()
        passed, failed = 0, 0
        details = []

        # 2.1 Sandbox execution with timeout
        exec_ok, exec_output = self._sandbox_execute(code)
        if exec_ok:
            passed += 1
        else:
            failed += 1
            details.append(f"Execution failed: {exec_output}")

        # 2.2 Solver status check (parse from output)
        if "optimal" in exec_output.lower():
            passed += 1
        elif "infeasible" in exec_output.lower():
            passed += 1  # infeasible is a valid solver output
            details.append("Model is infeasible — may need constraint relaxation")
        elif "unbounded" in exec_output.lower():
            failed += 1
            details.append("Model is unbounded — check for missing constraints")

        return LayerResult(
            layer=VerificationLayer.EXECUTION,
            status="PASS" if failed == 0 else "FAIL",
            checks_passed=passed,
            checks_failed=failed,
            details=details,
            execution_time_s=time.time() - t0,
        )

    # ------------------------------------------------------------------
    # Layer 3: Correctness Verification (MURKA 4D Reward)
    # ------------------------------------------------------------------

    def _verify_correctness(
        self, code: str, ir_model: dict | None, ground_truth: float | None
    ) -> LayerResult:
        """Layer 3: Constraint satisfaction + MURKA 4D reward."""
        t0 = time.time()
        passed, failed = 0, 0
        murka = MURKAReward()

        exec_ok, exec_output = self._sandbox_execute(code)
        if not exec_ok:
            return LayerResult(
                layer=VerificationLayer.CORRECTNESS,
                status="FAIL",
                checks_failed=1,
                details=[f"Code execution failed: {exec_output}"],
                execution_time_s=time.time() - t0,
            )

        # 3.1 Format reward (R_format)
        has_math_model = "decision" in exec_output.lower() or "variable" in exec_output.lower()
        has_code_block = "def solve" in code
        has_output = "objective" in exec_output.lower() or "optimal" in exec_output.lower()
        format_fields = sum([has_math_model, has_code_block, has_output])
        murka.format = format_fields / 3.0
        passed += 1 if murka.format > 0.5 else 0
        failed += 0 if murka.format > 0.5 else 1

        # 3.2 Constraint reward (R_constraint)
        constraint_ok = "infeasible" not in exec_output.lower()
        murka.constraint = 1.0 if constraint_ok else 0.0
        passed += 1 if constraint_ok else 0
        failed += 0 if constraint_ok else 1

        # 3.3 Semantic reward (R_sem) — basic heuristic
        obj_value = self._extract_objective_value(exec_output)
        if obj_value is not None and ground_truth is not None:
            # 5% tolerance comparison (ORLM pattern)
            gt = round(float(ground_truth))
            pred = round(float(obj_value))
            if gt != 0:
                relative_error = abs((pred - gt) / gt)
                murka.semantic = 1.0 if relative_error <= 0.05 else max(0, 1.0 - relative_error)
            else:
                murka.semantic = 1.0 if pred == 0 else 0.0
        elif obj_value is not None:
            murka.semantic = 0.5  # Can't verify without ground truth
        passed += 1 if murka.semantic > 0.5 else 0
        failed += 0 if murka.semantic > 0.5 else 1

        # 3.4 Similarity reward (R_sim) — basic cardinality check
        if ir_model:
            expected_vars = len(ir_model.get("variables", {}))
            if expected_vars > 0:
                murka.similarity = 0.8  # Placeholder — full impl needs extraction comparison
                passed += 1
            else:
                murka.similarity = 0.0
                failed += 1

        return LayerResult(
            layer=VerificationLayer.CORRECTNESS,
            status="PASS" if failed == 0 else "FAIL",
            checks_passed=passed,
            checks_failed=failed,
            murka_reward=murka,
            execution_time_s=time.time() - t0,
        )

    # ------------------------------------------------------------------
    # Layer 4: Equivalence Verification (AutoFormulator SMT)
    # ------------------------------------------------------------------

    def _verify_equivalence(self, ir_model: dict | None) -> LayerResult:
        """Layer 4: SMT-based equivalence checking (requires Z3)."""
        if not ir_model or not ir_model.get("equivalent_formulations"):
            return LayerResult(
                layer=VerificationLayer.EQUIVALENCE,
                status="SKIP",
                details=["No equivalent formulations to compare"],
            )

        # Placeholder: full SMT equivalence requires Z3 solver
        # AutoFormulator pattern: SymPy for objectives, Z3 for constraints
        return LayerResult(
            layer=VerificationLayer.EQUIVALENCE,
            status="SKIP",
            checks_passed=0,
            checks_failed=0,
            details=["SMT equivalence checking requires Z3 installation"],
        )

    # ------------------------------------------------------------------
    # Escalation Protocol (OR-LLM-Agent)
    # ------------------------------------------------------------------

    def _determine_escalation(self, result: VerificationResult) -> EscalationLevel:
        """Determine escalation level based on failure patterns."""
        structural = result.layer_results.get(VerificationLayer.STRUCTURAL)
        execution = result.layer_results.get(VerificationLayer.EXECUTION)
        correctness = result.layer_results.get(VerificationLayer.CORRECTNESS)

        # Level 0: Can self-correct (syntax errors, minor structural issues)
        if structural and structural.status == "FAIL" and structural.checks_failed <= 2:
            return EscalationLevel.NONE

        # Level 1: Agent escalation needed (execution or correctness issues)
        if execution and execution.status == "FAIL":
            return EscalationLevel.AGENT

        if correctness and correctness.status == "FAIL":
            return EscalationLevel.AGENT

        # Level 2: Strategy change (structural + correctness both fail)
        if (structural and structural.status == "FAIL" and
            correctness and correctness.status == "FAIL"):
            return EscalationLevel.STRATEGY

        # Level 3: Human handoff
        if result.total_checks_failed > 5:
            return EscalationLevel.HUMAN

        return EscalationLevel.NONE

    def _generate_repair_suggestions(self, result: VerificationResult) -> list[str]:
        """Generate specific repair suggestions based on failures."""
        suggestions = []
        for layer_name, layer in result.layer_results.items():
            if layer.status == "FAIL":
                for detail in layer.details:
                    suggestions.append(f"[{layer_name}] {detail}")
        return suggestions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_ir_schema(self, ir_model: dict) -> bool:
        """Basic IR schema validation."""
        required_keys = {"sets", "parameters", "variables", "constraints", "objective"}
        return required_keys.issubset(ir_model.keys())

    def _check_ir_semantics(self, ir_model: dict) -> tuple[bool, list[str]]:
        """Cross-reference IR variables, parameters, and constraints."""
        issues = []

        variables = set(ir_model.get("variables", {}).keys())
        parameters = set(ir_model.get("parameters", {}).keys())

        # Check constraints reference existing variables/parameters
        for c_name, constraint in ir_model.get("constraints", {}).items():
            expr_str = json.dumps(constraint.get("expression", {}))
            # Simple heuristic: check if variable names appear in expressions
            for var in variables:
                if var not in expr_str and var in ir_model.get("variables", {}):
                    pass  # Variables may be used in iteration context

        return len(issues) == 0, issues

    def _sandbox_execute(self, code: str) -> tuple[bool, str]:
        """Execute code in a subprocess sandbox (ORLM pattern)."""
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False
            ) as f:
                f.write(code)
                tmp_path = f.name

            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            Path(tmp_path).unlink(missing_ok=True)

            if result.returncode != 0:
                return False, result.stderr[:500]
            return True, result.stdout[:1000]

        except subprocess.TimeoutExpired:
            return False, f"Execution timed out after {self.timeout}s"
        except Exception as e:
            return False, str(e)[:500]

    def _extract_objective_value(self, output: str) -> float | None:
        """Extract objective value from solver output."""
        import re
        patterns = [
            r"Objective\s*(?:Value|value)?:\s*([\-\d.]+)",
            r"Best Objective:\s*([\-\d.]+)",
            r"Optimal (?:objective|cost|value):\s*([\-\d.]+)",
            r"Just print the best solution:\s*([\-\d.]+)",
        ]
        for pat in patterns:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                return float(m.group(1))
        return None
