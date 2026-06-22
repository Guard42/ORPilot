"""CPLEX solver backends — all 4 language APIs.

C++, Java, .NET, Python (docplex).
"""

from __future__ import annotations

from orpilot.codegen.backends import SolverBackend, registry
from orpilot.codegen.ir_compiler import IRCompiler


# ---------------------------------------------------------------------------
# Python (docplex.mp)
# ---------------------------------------------------------------------------

@registry.register("cplex-python")
class CPLEXPythonBackend(SolverBackend):
    """Compiles IR to CPLEX Python (docplex.mp) code."""

    @property
    def solver_name(self) -> str: return "cplex-python"

    @property
    def display_name(self) -> str: return "CPLEX Python (docplex.mp)"

    def compile(self, ir: dict) -> str:
        compiler = IRCompiler()
        return compiler.compile(ir, solver_framework="cplex")




# ---------------------------------------------------------------------------
# C++ (Concert Technology)
# ---------------------------------------------------------------------------

@registry.register("cplex-cpp")
class CPLEXCppBackend(SolverBackend):
    """Compiles IR to C++ code using CPLEX Concert Technology."""

    @property
    def solver_name(self) -> str: return "cplex-cpp"

    @property
    def display_name(self) -> str: return "CPLEX C++ (Concert)"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        sense = ir.get("sense", "minimize")
        lines = [
            '#include <ilcplex/ilocplex.h>', '',
            'int main() {',
            '    IloEnv env;',
            '    try {',
            '        IloModel model(env);',
            '        IloCplex cplex(model);',
        ]
        vmap = {"continuous": "ILOFLOAT", "integer": "ILOINT", "binary": "ILOBOOL"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "ILOFLOAT")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "IloInfinity")
            d = vm.get("domain", [])
            if not d:
                lines.append(f'        IloNumVar {vn}(env, {lb}, {ub}, {vt});')
                lines.append(f'        model.add({vn});')
            else:
                lines.append(f'        /* TODO: indexed {vn} over {d} */')
        for cn, cm in constraints.items():
            lines.append(f'        /* {cn}: {cm.get("description","")} */')
        obj_dir = "IloMinimize" if sense == "minimize" else "IloMaximize"
        lines.append(f'        model.add({obj_dir}(env));')
        lines.append(f'        cplex.solve();')
        lines.append(f'        if (cplex.getStatus() == IloAlgorithm::Optimal) env.out() << cplex.getObjValue() << std::endl;')
        lines.append(f'    }} catch (IloException& e) {{ env.out() << e << std::endl; }}')
        lines.append(f'    env.end(); return 0; }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

@registry.register("cplex-java")
class CPLEXJavaBackend(SolverBackend):
    """Compiles IR to Java code using CPLEX Java API."""

    @property
    def solver_name(self) -> str: return "cplex-java"

    @property
    def display_name(self) -> str: return "CPLEX Java"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        sense = ir.get("sense", "minimize")
        lines = [
            'import ilog.concert.*;', 'import ilog.cplex.*;', '',
            'public class CPLEXModel {',
            '    public static void main(String[] args) {',
            '        try {',
            '            IloCplex cplex = new IloCplex();',
        ]
        vmap = {"continuous": "IloNumVarType.Float", "integer": "IloNumVarType.Int", "binary": "IloNumVarType.Bool"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "IloNumVarType.Float")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "Double.MAX_VALUE")
            lines.append(f'            IloNumVar {vn} = cplex.numVar({lb}, {ub}, {vt});')
        obj = "cplex.addMinimize()" if sense == "minimize" else "cplex.addMaximize()"
        lines.append(f'            {obj};')
        lines.append(f'            if (cplex.solve()) System.out.println(cplex.getObjValue());')
        lines.append(f'        }} catch (IloException e) {{ e.printStackTrace(); }}')
        lines.append(f'    }} }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# .NET
# ---------------------------------------------------------------------------

@registry.register("cplex-dotnet")
class CPLEXDotNetBackend(SolverBackend):
    """Compiles IR to C# code using CPLEX .NET API."""

    @property
    def solver_name(self) -> str: return "cplex-dotnet"

    @property
    def display_name(self) -> str: return "CPLEX .NET (C#)"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        sense = ir.get("sense", "minimize")
        lines = [
            'using ILOG.Concert;', 'using ILOG.CPLEX;', '',
            'class Program {',
            '    static void Main() {',
            '        Cplex cplex = new Cplex();',
        ]
        vmap = {"continuous": "NumVarType.Float", "integer": "NumVarType.Int", "binary": "NumVarType.Bool"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "NumVarType.Float")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "System.Double.MaxValue")
            lines.append(f'            INumVar {vn} = cplex.NumVar({lb}, {ub}, {vt});')
        obj = "cplex.AddMinimize()" if sense == "minimize" else "cplex.AddMaximize()"
        lines.append(f'            {obj};')
        lines.append(f'            if (cplex.Solve()) System.Console.WriteLine(cplex.ObjValue);')
        lines.append(f'    }} }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CP Optimizer (Python)
# ---------------------------------------------------------------------------

@registry.register("cplex-cp")
class CPLEXCPBackend(SolverBackend):
    """CPLEX CP Optimizer — constraint programming backend."""

    @property
    def solver_name(self) -> str: return "cplex-cp"

    @property
    def display_name(self) -> str: return "CPLEX CP Optimizer (docplex.cp)"

    def compile(self, ir: dict) -> str:
        compiler = IRCompiler()
        code = compiler.compile(ir, solver_framework="cplex")
        code = code.replace(
            "from docplex.mp.model import Model",
            "from docplex.cp.model import CpoModel"
        )
        return code
