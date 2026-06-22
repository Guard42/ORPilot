"""PuLP solver backend."""

from __future__ import annotations

from orpilot.codegen.backends import SolverBackend, registry
from orpilot.codegen.ir_compiler import IRCompiler


@registry.register("pulp")
class PuLPBackend(SolverBackend):
    """Compiles IR to PuLP (CBC) code."""

    @property
    def solver_name(self) -> str:
        return "pulp"

    def compile(self, ir: dict) -> str:
        compiler = IRCompiler()
        return compiler.compile(ir, solver_framework="pulp")
