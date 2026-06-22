from .ir_compiler import IRCompiler
from .executor import CodeExecutor

# Auto-discover solver backends (LLVM TargetRegistry pattern)
from .backends import registry as solver_registry
from .backends import SolverBackend

# Gurobi — C, C++, Java, .NET, Python, MATLAB, R (7 languages)
from .backends import gurobi as _       # noqa: F401
# CPLEX — C++, Java, .NET, Python (4 languages)
from .backends import cplex as _        # noqa: F401
# OR-Tools — C++, Java, .NET, Python (4 languages)
from .backends import ortools as _      # noqa: F401
# PuLP — Python
from .backends import pulp as _         # noqa: F401
# Pyomo — Python
from .backends import pyomo as _        # noqa: F401

__all__ = [
    "IRCompiler",
    "CodeExecutor",
    "solver_registry",
    "SolverBackend",
]
