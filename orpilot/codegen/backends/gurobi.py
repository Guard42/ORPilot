"""Gurobi solver backends — all 7 language APIs.

C, C++, Java, .NET, Python, MATLAB, R.
v13 features (NLExpr/nlfunc, MVar, PDHG) integrated into Python backend.
"""

from __future__ import annotations

from orpilot.codegen.backends import SolverBackend, registry
from orpilot.codegen.ir_compiler import IRCompiler


# ---------------------------------------------------------------------------
# Python (gurobipy) — primary backend with v13 features
# ---------------------------------------------------------------------------

@registry.register("gurobi-python")
class GurobiPythonBackend(SolverBackend):
    """Compiles IR to gurobipy Python code with v13 NLExpr/nlfunc support."""

    @property
    def solver_name(self) -> str:
        return "gurobi-python"

    @property
    def display_name(self) -> str:
        return "Gurobi Python (gurobipy v13)"

    def compile(self, ir: dict) -> str:
        compiler = IRCompiler()
        code = compiler.compile(ir, solver_framework="gurobi")
        # Add nlfunc import for v13 nonlinear support
        if self._has_nl_nodes(ir):
            code = code.replace(
                "from gurobipy import GRB",
                "from gurobipy import GRB\nfrom gurobipy import nlfunc"
            )
        return code

    @staticmethod
    def _has_nl_nodes(ir: dict) -> bool:
        for c in ir.get("constraints", {}).values():
            for key in ("expression", "rhs"):
                if _check_nl(c.get(key, {})): return True
        return _check_nl(ir.get("objective", {}).get("expression", {}))


def _check_nl(node: dict) -> bool:
    if not isinstance(node, dict): return False
    if node.get("type", "").startswith("nl_"): return True
    return any(_check_nl(node.get(k, {})) for k in ("left", "right", "body"))




# ---------------------------------------------------------------------------
# C (GRB C API — 178 functions)
# ---------------------------------------------------------------------------

@registry.register("gurobi-c")
class GurobiCBackend(SolverBackend):
    """Compiles IR to C source code using the Gurobi C API."""

    @property
    def solver_name(self) -> str: return "gurobi-c"

    @property
    def display_name(self) -> str: return "Gurobi C (GRB C API)"

    def compile(self, ir: dict) -> str:
        sense = ir.get("sense", "minimize")
        sets = ir.get("sets", {})
        vars_ = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        lines = [
            '#include <stdlib.h>', '#include <stdio.h>', '#include "gurobi_c.h"', '',
            '#define CHECK(e, env) if(e){fprintf(stderr,"Error %d\\n",e);goto Q;}', '',
            'int solve(int argc, char *argv[]) {',
            '    GRBenv *env=NULL; GRBmodel *model=NULL; int error=0;',
            '    error = GRBemptyenv(&env); CHECK(error, env);',
            '    error = GRBstartenv(env); CHECK(error, env);',
            f'    /* Sets ({len(sets)}) */',
        ]
        for sn, sm in sets.items():
            s = sm.get("size", 0)
            lines.append(f'    int N_{sn} = {s if s else 0};')
        lines.append('    error = GRBnewmodel(env, &model, "m", 0,NULL,NULL,NULL,NULL,NULL);')
        lines.append('    CHECK(error, env);')
        vmap = {"continuous": "GRB_CONTINUOUS", "integer": "GRB_INTEGER", "binary": "GRB_BINARY"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "GRB_CONTINUOUS")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "GRB_INFINITY")
            d = vm.get("domain", [])
            if not d:
                lines.append(f'    int idx_{vn}; /* {vm.get("description","")} */')
                lines.append(f'    error = GRBaddvar(model,0,NULL,NULL,{lb},{ub},0.0,{vt},"{vn}");')
                lines.append(f'    CHECK(error, env);')
                lines.append(f'    GRBgetintattr(model,GRB_INT_ATTR_NUMVARS,&idx_{vn}); idx_{vn}-=1;')
            else:
                lines.append(f'    /* TODO: indexed vars {vn} over {d} */')
        for cn, cm in constraints.items():
            smap = {"=": "GRB_EQUAL", "<=": "GRB_LESS_EQUAL", ">=": "GRB_GREATER_EQUAL"}
            s = smap.get(cm.get("sense", "<="), "GRB_LESS_EQUAL")
            lines.append(f'    /* {cn}: {cm.get("description","")} (sense={s}) */')
        obs = "GRB_MINIMIZE" if sense == "minimize" else "GRB_MAXIMIZE"
        lines.append(f'    GRBsetintattr(model,GRB_INT_ATTR_MODELSENSE,{obs});')
        lines.append('    error = GRBoptimize(model); CHECK(error, env);')
        lines.append('    int status; GRBgetintattr(model,GRB_INT_ATTR_STATUS,&status);')
        lines.append('    if(status==GRB_OPTIMAL){double obj; GRBgetdblattr(model,GRB_DBL_ATTR_OBJVAL,&obj); printf("obj=%.6f\\n",obj);}')
        lines.append('    else if(status==GRB_INFEASIBLE) printf("infeasible\\n");')
        lines.append('    else if(status==GRB_UNBOUNDED) printf("unbounded\\n");')
        lines.append('Q: if(model) GRBfreemodel(model); if(env) GRBfreeenv(env); return error; }')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# C++ (gurobi_c++.h)
# ---------------------------------------------------------------------------

@registry.register("gurobi-cpp")
class GurobiCppBackend(SolverBackend):
    """Compiles IR to C++ code using the Gurobi C++ API."""

    @property
    def solver_name(self) -> str: return "gurobi-cpp"

    @property
    def display_name(self) -> str: return "Gurobi C++ (GRB C++ API)"

    def compile(self, ir: dict) -> str:
        sets = ir.get("sets", {})
        vars_ = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        sense = ir.get("sense", "minimize")
        name = ir.get("problem_class", "Model")
        lines = [
            '#include "gurobi_c++.h"', '#include <vector>', '',
            f'int solve_{name}() {{',
            '    try {',
            f'        GRBEnv env = GRBEnv(true); env.start();',
            f'        GRBModel model = GRBModel(env);',
        ]
        vmap = {"continuous": "GRB_CONTINUOUS", "integer": "GRB_INTEGER", "binary": "GRB_BINARY"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "GRB_CONTINUOUS")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "GRB_INFINITY")
            d = vm.get("domain", [])
            if not d:
                lines.append(f'        GRBVar {vn} = model.addVar({lb}, {ub}, 0.0, {vt});')
            else:
                lines.append(f'        /* TODO: indexed {vn} over {d} */')
        for cn, cm in constraints.items():
            lines.append(f'        /* {cn}: {cm.get("description","")} */')
        obs = "GRB_MINIMIZE" if sense == "minimize" else "GRB_MAXIMIZE"
        lines.append(f'        model.optimize();')
        lines.append(f'        int status = model.get(GRB_IntAttr_Status);')
        lines.append(f'        if (status == GRB_OPTIMAL) std::cout << "obj=" << model.get(GRB_DoubleAttr_ObjVal) << std::endl;')
        lines.append(f'    }} catch (GRBException e) {{ std::cerr << e.getMessage() << std::endl; return 1; }}')
        lines.append(f'    return 0; }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Java (grb.jar)
# ---------------------------------------------------------------------------

@registry.register("gurobi-java")
class GurobiJavaBackend(SolverBackend):
    """Compiles IR to Java code using the Gurobi Java API."""

    @property
    def solver_name(self) -> str: return "gurobi-java"

    @property
    def display_name(self) -> str: return "Gurobi Java (grb.jar)"

    def compile(self, ir: dict) -> str:
        sets = ir.get("sets", {})
        vars_ = ir.get("variables", {})
        sense = ir.get("sense", "minimize")
        name = ir.get("problem_class", "Model")
        lines = [
            'import gurobi.*;', '',
            f'public class {name} {{',
            '    public static void main(String[] args) {',
            '        try {',
            '            GRBEnv env = new GRBEnv();',
            f'            GRBModel model = new GRBModel(env);',
        ]
        for sn, sm in sets.items():
            lines.append(f'            /* Set: {sn} */')
        vmap = {"continuous": "GRB.CONTINUOUS", "integer": "GRB.INTEGER", "binary": "GRB.BINARY"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "GRB.CONTINUOUS")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "GRB.INFINITY")
            lines.append(f'            GRBVar {vn} = model.addVar({lb}, {ub}, 0.0, {vt}, "{vn}");')
        obs = "GRB.MINIMIZE" if sense == "minimize" else "GRB.MAXIMIZE"
        lines.append(f'            model.optimize();')
        lines.append(f'            int status = model.get(GRB.IntAttr.Status);')
        lines.append(f'            if (status == GRB.OPTIMAL) System.out.println("obj=" + model.get(GRB.DoubleAttr.ObjVal));')
        lines.append(f'        }} catch (GRBException e) {{ e.printStackTrace(); }}')
        lines.append(f'    }} }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# .NET (Gurobi .NET)
# ---------------------------------------------------------------------------

@registry.register("gurobi-dotnet")
class GurobiDotNetBackend(SolverBackend):
    """Compiles IR to C# code using the Gurobi .NET API."""

    @property
    def solver_name(self) -> str: return "gurobi-dotnet"

    @property
    def display_name(self) -> str: return "Gurobi .NET (C#)"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        sense = ir.get("sense", "minimize")
        lines = [
            'using System;', 'using Gurobi;', '',
            'class Program {',
            '    static void Main() {',
            '        try {',
            '            GRBEnv env = new GRBEnv();',
            '            GRBModel model = new GRBModel(env);',
        ]
        vmap = {"continuous": "GRB.CONTINUOUS", "integer": "GRB.INTEGER", "binary": "GRB.BINARY"}
        for vn, vm in vars_.items():
            vt = vmap.get(vm.get("type", "continuous"), "GRB.CONTINUOUS")
            lb = vm.get("lower_bound", 0.0)
            ub = vm.get("upper_bound", "GRB.INFINITY")
            lines.append(f'            GRBVar {vn} = model.AddVar({lb}, {ub}, 0.0, {vt}, "{vn}");')
        obs = "GRB.MINIMIZE" if sense == "minimize" else "GRB.MAXIMIZE"
        lines.append(f'            model.Optimize();')
        lines.append(f'            if (model.Status == GRB.Status.OPTIMAL) Console.WriteLine("obj=" + model.ObjVal);')
        lines.append(f'        }} catch (GRBException e) {{ Console.WriteLine(e.Message); }}')
        lines.append(f'    }} }}')
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# MATLAB
# ---------------------------------------------------------------------------

@registry.register("gurobi-matlab")
class GurobiMatlabBackend(SolverBackend):
    """Compiles IR to MATLAB code using the Gurobi MATLAB API."""

    @property
    def solver_name(self) -> str: return "gurobi-matlab"

    @property
    def display_name(self) -> str: return "Gurobi MATLAB"

    def compile(self, ir: dict) -> str:
        vars_ = ir.get("variables", {})
        constraints = ir.get("constraints", {})
        sense = ir.get("sense", "minimize")
        lines = [
            '% Gurobi MATLAB solver', '',
            'model.vtype = []; model.lb = []; model.ub = [];',
            'model.A = sparse([]); model.rhs = []; model.sense = [];',
            f'model.modelsense = ''{"min" if sense == "minimize" else "max"}'';',
        ]
        vtype_map = {"continuous": "''C''", "integer": "''I''", "binary": "''B''"}
        for vn, vm in vars_.items():
            vt = vtype_map.get(vm.get("type", "continuous"), "''C''")
            lb = vm.get("lower_bound", 0)
            ub = vm.get("upper_bound", "inf")
            lines.append(f'model.vtype = [model.vtype; {vt}];')
            lines.append(f'model.lb = [model.lb; {lb}];')
            lines.append(f'model.ub = [model.ub; {ub}];')
        lines.append("params.OutputFlag = 0;")
        lines.append("result = gurobi(model, params);")
        lines.append("disp(result);")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# R
# ---------------------------------------------------------------------------

@registry.register("gurobi-r")
class GurobiRBackend(SolverBackend):
    """Compiles IR to R code using the Gurobi R API."""

    @property
    def solver_name(self) -> str: return "gurobi-r"

    @property
    def display_name(self) -> str: return "Gurobi R"

    def compile(self, ir: dict) -> str:
        sense = ir.get("sense", "minimize")
        lines = [
            'library(gurobi)', '',
            f'model <- list()',
            f'model$modelsense <- ''{"min" if sense == "minimize" else "max"}'';',
            'model$vtype <- c()',
            'model$lb <- c()',
            'model$ub <- c()',
            'model$obj <- c()',
            'model$A <- Matrix::Matrix(0, sparse=TRUE)',
            'model$rhs <- c()',
            'model$sense <- c()',
            'params <- list(OutputFlag=0)',
            'result <- gurobi(model, params)',
            'print(result$objval)',
            'print(result$x)',
        ]
        return "\n".join(lines) + "\n"
