"""Abstract base class for OR solvers."""

from abc import ABC, abstractmethod

from orpilot.models.solution import SolutionResult


class BaseSolver(ABC):
    """Unified interface for OR solvers."""

    name: str = "base"
    framework: str = "base"

    @abstractmethod
    def solve(self, code: str, data: dict, time_limit: int | None = None, show_solver_log: bool = False) -> SolutionResult:
        """Execute solver code with the given data and return results.

        Args:
            code: Python source code containing a `solve(data) -> dict` function.
            data: Data dictionary to pass to the solve function.
            time_limit: Optional solver time limit in seconds. The solver stops
                early and returns the best feasible solution found so far.

        Returns:
            SolutionResult with status, objective value, variables, etc.
        """
        ...
