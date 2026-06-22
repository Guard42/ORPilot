"""OR-Tools solver backends — all 4 language APIs.

C++, .NET (C#), Java, Python.
"""

from __future__ import annotations

from orpilot.codegen.backends import SolverBackend, registry
from orpilot.codegen.ir_compiler import IRCompiler


# ---------------------------------------------------------------------------
# Python (pywraplp)
# ---------------------------------------------------------------------------

@registry.register("ortools-python")
class ORToolsPythonBackend(SolverBackend):
    """Compiles IR to OR-Tools Python (pywraplp) code."""

    @property
    def solver_name(self) -> str: return "ortools-python"

    @property
    def display_name(self) -> str: return "OR-Tools Python (pywraplp)"

    def compile(self, ir: dict) -> str:
        compiler = IRCompiler()
        return compiler.compile(ir, solver_framework="ortools")




# ---------------------------------------------------------------------------
# C++ (MPSolver)
# ---------------------------------------------------------------------------

@registry.register("ortools-cpp")
class ORToolsCppBackend(SolverBackend):
    """Compiles IR to C++ code using OR-Tools MPSolver."""

    @property
    def solver_name(self) -> str: return "ortools-cpp"

    @property
    def display_name(self) -> str: return "OR-Tools C++ (MPSolver)"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        sense = ir.get("sense", "minimize")
        lines = [
            '#include "ortools/linear_solver/linear_solver.h"', '',
            'namespace op = operations_research;', '',
            'int main() {',
            '    auto solver = op::MPSolver::CreateSolver("SCIP");',
        ]
        for vn, vm in vars_.items():
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "solver->infinity()")
            vt = vm.get("type", "continuous")
            if vt == "integer":
                lines.append(f'    op::MPVariable* {vn} = solver->MakeIntVar({lb}, {ub}, "{vn}");')
            elif vt == "binary":
                lines.append(f'    op::MPVariable* {vn} = solver->MakeBoolVar("{vn}");')
            else:
                lines.append(f'    op::MPVariable* {vn} = solver->MakeNumVar({lb}, {ub}, "{vn}");')
        for cn, cm in constraints.items():
            lines.append(f'    /* {cn}: {cm.get("description","")} */')
            lines.append(f'    op::MPConstraint* c_{cn} = solver->MakeRowConstraint();')
        obs = "solver->MutableObjective()->SetMinimization();" if sense == "minimize" else "solver->MutableObjective()->SetMaximization();"
        lines.append(f'    {obs}')
        lines.append(f'    solver->Solve();')
        lines.append(f'    std::cout << solver->Objective().Value() << std::endl;')
        lines.append(f'    delete solver; return 0; }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

@registry.register("ortools-java")
class ORToolsJavaBackend(SolverBackend):
    """Compiles IR to Java code using OR-Tools MPSolver."""

    @property
    def solver_name(self) -> str: return "ortools-java"

    @property
    def display_name(self) -> str: return "OR-Tools Java (MPSolver)"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        sense = ir.get("sense", "minimize")
        lines = [
            'import com.google.ortools.Loader;',
            'import com.google.ortools.linearsolver.*;', '',
            'public class ORToolsModel {',
            '    static { Loader.loadNativeLibraries(); }',
            '    public static void main(String[] args) {',
            '        MPSolver solver = MPSolver.createSolver("SCIP");',
        ]
        for vn, vm in vars_.items():
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "Double.POSITIVE_INFINITY")
            vt = vm.get("type", "continuous")
            if vt == "integer":
                lines.append(f'        MPVariable {vn} = solver.makeIntVar({lb}, {ub}, "{vn}");')
            elif vt == "binary":
                lines.append(f'        MPVariable {vn} = solver.makeBoolVar("{vn}");')
            else:
                lines.append(f'        MPVariable {vn} = solver.makeNumVar({lb}, {ub}, "{vn}");')
        obs = "solver.objective().setMinimization();" if sense == "minimize" else "solver.objective().setMaximization();"
        lines.append(f'        {obs}')
        lines.append(f'        solver.solve();')
        lines.append(f'        System.out.println(solver.objective().value());')
        lines.append(f'    }} }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# .NET (C#)
# ---------------------------------------------------------------------------

@registry.register("ortools-dotnet")
class ORToolsDotNetBackend(SolverBackend):
    """Compiles IR to C# code using OR-Tools MPSolver."""

    @property
    def solver_name(self) -> str: return "ortools-dotnet"

    @property
    def display_name(self) -> str: return "OR-Tools .NET (C#)"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        sense = ir.get("sense", "minimize")
        lines = [
            'using Google.OrTools.LinearSolver;', '',
            'class Program {',
            '    static void Main() {',
            '        Solver solver = Solver.CreateSolver("SCIP");',
        ]
        for vn, vm in vars_.items():
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "double.PositiveInfinity")
            vt = vm.get("type", "continuous")
            if vt == "integer":
                lines.append(f'        Variable {vn} = solver.MakeIntVar({lb}, {ub}, "{vn}");')
            elif vt == "binary":
                lines.append(f'        Variable {vn} = solver.MakeBoolVar("{vn}");')
            else:
                lines.append(f'        Variable {vn} = solver.MakeNumVar({lb}, {ub}, "{vn}");')
        obs = "solver.Objective().SetMinimization();" if sense == "minimize" else "solver.Objective().SetMaximization();"
        lines.append(f'        {obs}')
        lines.append(f'        solver.Solve();')
        lines.append(f'        System.Console.WriteLine(solver.Objective().Value());')
        lines.append(f'    }} }}')
        return "\n".join(lines) + "\n"
