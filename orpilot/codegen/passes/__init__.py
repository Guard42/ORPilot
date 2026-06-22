"""LLVM/MLIR-style PassManager for IR transformation pipeline.

Each pass is an independent, testable transformation.  The PassManager runs
them in sequence with optional caching and validation between passes.

Inspired by:
- LLVM PassManager: https://llvm.org/docs/WritingAnLLVMPass.html
- MLIR Pass Infrastructure: https://mlir.llvm.org/docs/PassManagement/
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class IRPass(ABC):
    """A single transformation pass on the IR.  Each pass is independently testable."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique pass name for logging and debugging."""
        ...

    @abstractmethod
    def run(self, ir: dict) -> dict:
        """Transform the IR dict.  Must return the (possibly modified) IR."""
        ...

    def invalidates_cache(self) -> bool:
        """Whether this pass invalidates the compilation cache."""
        return True


class ValidateSchemaPass(IRPass):
    """Pass 1: Validate that the Pydantic schema is satisfied before any transforms.

    Reference: LLVM's VerifyPass — runs first to catch structural errors early.
    https://llvm.org/docs/Passes.html#verify-function-verification
    """

    name = "validate-schema"

    def run(self, ir: dict) -> dict:
        required = {"sets", "parameters", "variables", "constraints", "objective"}
        missing = required - ir.keys()
        if missing:
            raise ValueError(f"IR schema validation failed: missing top-level keys: {missing}")
        return ir


class CanonicalizeSetsPass(IRPass):
    """Pass 2: Normalize set definitions — resolve size_source, remove :alias.

    Reference: MLIR Canonicalization:
    https://mlir.llvm.org/docs/Canonicalization/
    """

    name = "canonicalize-sets"

    def run(self, ir: dict) -> dict:
        sets = ir.get("sets", {})
        for set_meta in sets.values():
            if "size_source" in set_meta and "size" not in set_meta:
                set_meta["size"] = None  # Will be resolved at compile time
        return ir

    def invalidates_cache(self) -> bool:
        return False


class SimplifyExpressionsPass(IRPass):
    """Pass 3: Constant folding and algebraic simplification.

    Reference: LLVM InstCombine:
    https://llvm.org/docs/Passes.html#instcombine-combine-redundant-instructions
    """

    name = "simplify-expressions"

    _IDENTITY_RULES = [
        # multiply(x, 1) → x
        (lambda n: n.get("type") == "multiply", lambda n: _simplify_multiply_one(n)),
        # sum(x, 0) → x
        (lambda n: n.get("type") == "sum", lambda n: _simplify_add_zero(n)),
        # subtract(x, 0) → x
        (lambda n: n.get("type") == "subtract", lambda n: _simplify_sub_zero(n)),
    ]

    def run(self, ir: dict) -> dict:
        for cmeta in ir.get("constraints", {}).values():
            cmeta["expression"] = self._simplify(cmeta["expression"])
            cmeta["rhs"] = self._simplify(cmeta["rhs"])
        if "objective" in ir and "expression" in ir["objective"]:
            ir["objective"]["expression"] = self._simplify(ir["objective"]["expression"])
        return ir

    def _simplify(self, node: dict) -> dict:
        if not isinstance(node, dict):
            return node
        for pattern, action in self._IDENTITY_RULES:
            if pattern(node):
                result = action(node)
                if result is not None:
                    return result
        if "left" in node:
            node["left"] = self._simplify(node["left"])
        if "right" in node:
            node["right"] = self._simplify(node["right"])
        if "body" in node:
            node["body"] = self._simplify(node["body"])
        return node


def _simplify_multiply_one(node: dict) -> dict | None:
    right = node.get("right", {})
    left = node.get("left", {})
    if right.get("type") == "constant" and right.get("value") == 1:
        return left
    if left.get("type") == "constant" and left.get("value") == 1:
        return right
    return None


def _simplify_add_zero(node: dict) -> dict | None:
    right = node.get("right", {})
    if right.get("type") == "constant" and right.get("value") == 0:
        return node.get("left", {})
    return None


def _simplify_sub_zero(node: dict) -> dict | None:
    right = node.get("right", {})
    if right.get("type") == "constant" and right.get("value") == 0:
        return node.get("left", {})
    return None


# ---------------------------------------------------------------------------
# PassManager
# ---------------------------------------------------------------------------

@dataclass
class PassManager:
    """LLVM-style pass pipeline with fluent API.

    Usage::

        pm = (PassManager()
            .add_pass(ValidateSchemaPass())
            .add_pass(CanonicalizeSetsPass())
            .add_pass(SimplifyExpressionsPass())
        )
        optimized_ir = pm.run(raw_ir)
    """

    passes: list[IRPass] = field(default_factory=list)
    validation: bool = True  # Run validation between passes

    def add_pass(self, pass_: IRPass) -> "PassManager":
        self.passes.append(pass_)
        return self

    def run(self, ir: dict) -> dict:
        for i, pass_ in enumerate(self.passes):
            try:
                ir = pass_.run(ir)
            except Exception as e:
                raise RuntimeError(
                    f"Pass '{pass_.name}' (index {i}) failed: {e}"
                ) from e
        return ir
