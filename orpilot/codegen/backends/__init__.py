"""Solver backend plugin registry — LLVM TargetRegistry pattern.

New solver backends are registered via ``@registry.register("name")`` and
discovered automatically.  The core IR compiler never needs to be edited
when a new solver is added.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class SolverBackend(ABC):
    """Abstract solver backend — equivalent to LLVM's TargetMachine.

    Each concrete backend knows how to emit code for one specific solver
    (Gurobi, CPLEX, PuLP, Pyomo, OR-Tools, ...).
    """

    @abstractmethod
    def compile(self, ir: dict) -> str:
        """Compile IR dict to a complete, executable ``solve(data)`` function."""
        ...

    @property
    @abstractmethod
    def solver_name(self) -> str:
        """Unique solver identifier, e.g. ``"gurobi"``, ``"pulp"``."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for CLI / error messages."""
        return self.solver_name


class SolverRegistry:
    """Auto-discovering solver registry.

    Usage::

        @registry.register("highs")
        class HiGHSBackend(SolverBackend):
            ...
    """

    _backends: ClassVar[dict[str, type[SolverBackend]]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator that registers a solver backend class."""

        def _decorator(backend_cls: type[SolverBackend]) -> type[SolverBackend]:
            cls._backends[name] = backend_cls
            return backend_cls

        return _decorator

    @classmethod
    def get(cls, name: str) -> type[SolverBackend] | None:
        """Look up a registered backend by name."""
        return cls._backends.get(name)

    @classmethod
    def create(cls, name: str) -> SolverBackend:
        """Instantiate a backend by name."""
        backend_cls = cls.get(name)
        if backend_cls is None:
            available = ", ".join(sorted(cls.list_names()))
            raise ValueError(
                f"Unknown solver: {name!r}. Available: {available}"
            )
        return backend_cls()

    @classmethod
    def list_names(cls) -> list[str]:
        """Return sorted list of registered solver names."""
        return sorted(cls._backends.keys())

    @classmethod
    def list_backends(cls) -> dict[str, str]:
        """Return {name: display_name} for all registered backends."""
        return {
            name: backend().display_name
            for name, backend in cls._backends.items()
        }


# Global registry instance
registry = SolverRegistry()
