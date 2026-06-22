"""Pyomo solver backend."""

from __future__ import annotations

from orpilot.codegen.backends import SolverBackend, registry
from orpilot.codegen.ir_compiler import IRCompiler


@registry.register("pyomo")
class PyomoBackend(SolverBackend):
    """Compiles IR to Pyomo code."""

    @property
    def solver_name(self) -> str:
        return "pyomo"

    def compile(self, ir: dict) -> str:
        compiler = IRCompiler()
        return compiler.compile(ir, solver_framework="pyomo")
