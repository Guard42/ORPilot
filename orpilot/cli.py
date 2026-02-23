"""CLI entry point using Typer."""

from __future__ import annotations

import csv
import json
import os
import tomllib
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

# Load .env before Typer resolves envvar= options (e.g. OPENAI_API_KEY).
load_dotenv()
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from orpilot.llm.config import LLMConfig, get_llm
from orpilot.paths import DATA_DIR
from orpilot.workflow.graph import build_graph
from orpilot.workflow.state import WorkflowState
from orpilot.models.problem import ProblemDefinition
from orpilot.models.data import UserData

app = typer.Typer(
    name="orpilot",
    help="AI Operations Research Agent — LLM-powered OR modeling and solving",
)
console = Console()

_AUTO_CONFIG_NAMES = ("orpilot.toml", "orpilot.json")


def _load_config_file(path: Path) -> dict:
    """Load config values from a TOML or JSON file."""
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with open(path, "rb") as f:
        return tomllib.load(f)


def _discover_config_file() -> Path | None:
    """Locate a config file via ORPILOT_CONFIG env var or by walking up from CWD."""
    # 1. Explicit env var (absolute path, works regardless of working directory)
    env_path = os.environ.get("ORPILOT_CONFIG")
    if env_path:
        return Path(env_path)

    # 2. Walk up from CWD (like git looking for .git)
    current = Path.cwd()
    while True:
        for name in _AUTO_CONFIG_NAMES:
            candidate = current / name
            if candidate.exists():
                return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_NODE_LABELS: dict[str, tuple[str, str]] = {
    "interview": ("blue", "Conducting interview..."),
    "data_collection": ("blue", "Collecting data..."),
    "ir_builder": ("yellow", "Starting model building (translating problem to IR)..."),
    "ir_compiler": ("yellow", "Compiling IR to solver code..."),
    "solver_runner": ("yellow", "Starting model solving..."),
    "reporter": ("green", "Generating solution report..."),
}

_NODE_COMPLETE_LABELS: dict[str, tuple[str, str]] = {
    "interview": ("green", "Interview finished — problem defined."),
    "data_collection": ("green", "Data collection finished — all CSV files loaded."),
    "ir_builder": ("green", "IR model built."),
    "ir_compiler": ("green", "Model building finished — solver code ready."),
    "solver_runner": ("green", "Model solving finished."),
}


def _log_entering_node(node: str) -> None:
    """Print a status line when entering a workflow node."""
    style, msg = _NODE_LABELS.get(node, ("dim", f"Running {node}..."))
    console.print(f"[{style}]>> {msg}[/{style}]")


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------


def _save_artifacts(
    state: dict,
    output_dir: str,
    last_saved_code: str,
    con: Console,
) -> str:
    """Save generated code and LP file to output_dir. Returns the last saved code."""
    code = state.get("generated_code", "")
    out = Path(output_dir)

    # Save generated Python code whenever it changes
    if code and code != last_saved_code:
        model_path = out / "model.py"
        model_path.write_text(code, encoding="utf-8")
        con.print(f"[dim]  -> Saved generated code to {model_path}[/dim]")

    # Save IR model whenever it is available
    ir_model = state.get("ir_model")
    if ir_model:
        ir_path = out / "ir.json"
        ir_path.write_text(json.dumps(ir_model, indent=2), encoding="utf-8")
        con.print(f"[dim]  -> Saved IR to {ir_path}[/dim]")

    # Save LP file from solution if available
    solution = state.get("solution")
    if solution and solution.lp_content:
        lp_path = out / "model.lp"
        lp_path.write_text(solution.lp_content, encoding="utf-8")
        con.print(f"[dim]  -> Saved LP file to {lp_path}[/dim]")

    return code if code else last_saved_code


def _parse_variable_dimensions(
    variables: dict,
    group_name: str,
    dimension_labels: list[str] | None = None,
) -> tuple[list[str], list[list]]:
    """Parse variable names into dimension columns for a single variable group.

    Variable names follow the pattern ``prefix_dim1_dim2_...``.  The *prefix*
    (which equals *group_name*) is stripped — only dimension values and the
    solution value appear in the rows.

    Returns (headers, rows).
    """
    import re

    _SEP = "\x1f"  # Unit Separator — used by IR compiler to delimit dimensions

    parsed: list[tuple[list[str], object]] = []
    max_dims = 0

    for var_name, value in sorted(variables.items()):
        if _SEP in var_name:
            # Unambiguous delimiter: "prefix\x1fdim1\x1fdim2\x1f..."
            parts = var_name.split(_SEP, 1)
            dims = parts[1].split(_SEP) if len(parts) > 1 else []
        else:
            # Try tuple-style: ship_('WH1',_'CUST2')
            tuple_match = re.match(r"^([^(]+?)_?\((.+)\)$", var_name)
            if tuple_match:
                inner = tuple_match.group(2)
                dims = [
                    d.strip().strip("'\"").strip("_").strip()
                    for d in inner.split(",")
                    if d.strip().strip("'\"").strip("_").strip()
                ]
            else:
                # Legacy underscore-separated fallback (no underscores in IDs)
                parts = var_name.split("_")
                if len(parts) >= 2:
                    prefix_parts = group_name.split("_")
                    if parts[: len(prefix_parts)] == prefix_parts:
                        dims = parts[len(prefix_parts):]
                    else:
                        dims = parts[1:]
                else:
                    dims = []

        max_dims = max(max_dims, len(dims))
        parsed.append((dims, value))

    # Build headers
    labels = dimension_labels or []
    headers: list[str] = []
    for i in range(max_dims):
        if i < len(labels):
            headers.append(labels[i])
        else:
            headers.append(f"dim_{i + 1}")
    headers.append("value")

    # Build rows
    rows: list[list] = []
    for dims, value in parsed:
        row: list = []
        for i in range(max_dims):
            row.append(dims[i] if i < len(dims) else "")
        row.append(value)
        rows.append(row)

    return headers, rows


def _save_solution(state: dict, output_dir: str, con: Console) -> None:
    """Save objective value as txt and each variable group as its own CSV."""
    solution = state.get("solution")
    if not solution:
        return

    out = Path(output_dir)

    # Save optimization summary
    summary_path = out / "optimization_summary.txt"
    lines = [
        f"Status: {solution.status.value}",
    ]
    if solution.objective_value is not None:
        lines.append(f"Objective Value: {solution.objective_value}")
    if solution.solve_time_seconds is not None:
        lines.append(f"Solve Time: {solution.solve_time_seconds:.4f}s")
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    con.print(f"[dim]  -> Saved optimization summary to {summary_path}[/dim]")

    # Save one CSV per variable group
    if solution.variable_groups:
        for group in solution.variable_groups:
            if not group.variables:
                continue
            filename = f"solution_{group.group_name}.csv"
            csv_path = out / filename
            headers, rows = _parse_variable_dimensions(
                group.variables,
                group_name=group.group_name,
                dimension_labels=group.dimension_labels or None,
            )
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow(row)
            con.print(f"[dim]  -> Saved {group.group_name} solution values to {csv_path}[/dim]")
    elif solution.variables:
        # Fallback: no groups returned, dump all variables into a single CSV
        csv_path = out / "solution_decisions.csv"
        headers, rows = _parse_variable_dimensions(
            solution.variables,
            group_name="",
        )
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)
        con.print(f"[dim]  -> Saved decision variable solution values to {csv_path}[/dim]")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@app.command()
def run(
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to a TOML or JSON config file. CLI options take precedence. Auto-discovered if orpilot.toml exists in the current directory."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider (openai, anthropic)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name override"),
    solver: Optional[str] = typer.Option(None, "--solver", "-s", help="OR solver (pulp, pyomo, ortools)"),
    problem_file: Optional[Path] = typer.Option(None, "--problem", help="Load problem definition from JSON file"),
    data_file: Optional[Path] = typer.Option(None, "--data", help="Load data from JSON file"),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", "-d", help="Directory for CSV data files"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to save generated code, LP file, and solution"),
    max_retries: Optional[int] = typer.Option(None, "--max-retries", help="Max solver code retries"),
    time_limit: Optional[int] = typer.Option(None, "--time-limit", "-t", help="Max solver run time in seconds. Stops early and returns best solution found."),
    show_solver_log: Optional[bool] = typer.Option(None, "--solver-log/--no-solver-log", help="Stream the solver log to stdout."),
    verbose: Optional[bool] = typer.Option(None, "--verbose/--no-verbose", help="Show full solver and compiler error details"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="OPENAI_API_KEY"),
    base_url: Optional[str] = typer.Option(None, "--base-url", envvar="OPENAI_BASE_URL", help="Custom API base URL (e.g. https://api.deepseek.com)"),
) -> None:
    """Start an interactive ORPilot session."""
    # --- Load config file ---
    # Explicit --config takes priority; otherwise auto-discover orpilot.toml/json.
    cfg: dict = {}
    resolved_config = config_file
    if resolved_config is None:
        resolved_config = _discover_config_file()
    if resolved_config is not None:
        if not resolved_config.exists():
            console.print(f"[red]Config file not found: {resolved_config}[/red]")
            raise typer.Exit(1)
        cfg = _load_config_file(resolved_config)
        console.print(f"[dim]Loaded config from {resolved_config}[/dim]")

    # --- Merge: CLI values > config file values > hardcoded defaults ---
    provider        = provider        or cfg.get("provider",         "openai")
    model           = model           or cfg.get("model")
    solver          = solver          or cfg.get("solver",           "pulp")
    max_retries     = max_retries     if max_retries     is not None else cfg.get("max_retries",     3)
    time_limit      = time_limit      if time_limit      is not None else cfg.get("time_limit",      300)
    verbose         = verbose         if verbose         is not None else cfg.get("verbose",         False)
    show_solver_log = show_solver_log if show_solver_log is not None else cfg.get("show_solver_log", False)
    base_url        = base_url        or cfg.get("base_url")
    api_key         = api_key         or cfg.get("api_key")

    # Resolve path options: relative paths from a config file are relative to
    # the config file's directory; CLI-supplied paths are relative to CWD.
    cfg_dir = resolved_config.parent if resolved_config is not None else Path.cwd()
    if data_dir is None:
        data_dir = (cfg_dir / cfg["data_dir"]).resolve() if "data_dir" in cfg else DATA_DIR
    else:
        data_dir = data_dir.resolve()
    if output_dir is None and "output_dir" in cfg:
        output_dir = (cfg_dir / cfg["output_dir"]).resolve()
    elif output_dir is not None:
        output_dir = output_dir.resolve()

    llm_config = LLMConfig(provider=provider, model=model, api_key=api_key, base_url=base_url)
    llm = get_llm(llm_config)
    graph = build_graph(llm=llm)

    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)

    # Ensure output directory exists if specified
    output_dir_str = ""
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_dir_str = str(output_dir)

    # Initialize state
    state: WorkflowState = {
        "messages": [],
        "problem": None,
        "user_data": None,
        "ir_model": None,
        "generated_code": "",
        "solution": None,
        "report": "",
        "current_node": "interview",
        "solver_name": solver,
        "retry_count": 0,
        "max_retries": max_retries,
        "error_context": "",
        "needs_user_input": False,
        "user_input": "",
        "llm_config": llm_config.__dict__,
        "data_dir": str(data_dir),
        "csv_specs": [],
        "output_dir": output_dir_str,
        "solver_time_limit": time_limit,
        "show_solver_log": show_solver_log,
    }

    # Load problem from file if provided
    if problem_file and problem_file.exists():
        problem = ProblemDefinition.model_validate_json(problem_file.read_text())
        state["problem"] = problem
        state["current_node"] = "data_collection"
        console.print(Panel(f"Loaded problem: {problem.title}", title="Problem"))

    # Load data from file if provided
    if data_file and data_file.exists():
        data = UserData.model_validate_json(data_file.read_text())
        state["user_data"] = data
        if state.get("problem"):
            state["current_node"] = "ir_builder"
        console.print(Panel("Loaded data from file", title="Data"))

    console.print(Panel(
        "Welcome to ORPilot — AI Operations Research Agent\n"
        "I'll help you model and solve optimization problems.\n"
        "Type 'quit' to exit at any time.",
        title="ORPilot",
        border_style="blue",
    ))

    _last_saved_code = ""

    while True:
        # Stream the graph one node at a time so we can log each step.
        for chunk in graph.stream(state, stream_mode="updates"):
            for node_name, node_update in chunk.items():
                if node_name.startswith("__"):
                    continue

                prev_state = state
                state = {**state, **node_update}

                # wait_for_input is an infrastructure node — skip logging.
                if node_name == "wait_for_input":
                    continue

                # The interview node doubles as a router once the problem is
                # defined.  Suppress its "entering" log in that case.
                interview_passthrough = (
                    node_name == "interview"
                    and prev_state.get("problem") is not None
                )
                if not interview_passthrough:
                    _log_entering_node(node_name)

                # ── Milestone completion logging ──────────────────────────
                if node_name == "interview":
                    if (prev_state.get("problem") is None
                            and state.get("problem") is not None):
                        style, msg = _NODE_COMPLETE_LABELS["interview"]
                        console.print(f"[{style}]✓ {msg}[/{style}]")

                elif node_name == "data_collection":
                    if (prev_state.get("user_data") is None
                            and state.get("user_data") is not None):
                        style, msg = _NODE_COMPLETE_LABELS["data_collection"]
                        console.print(f"[{style}]✓ {msg}[/{style}]")

                elif node_name == "ir_builder":
                    if state.get("ir_model"):
                        style, msg = _NODE_COMPLETE_LABELS["ir_builder"]
                        console.print(f"[{style}]✓ {msg}[/{style}]")

                elif node_name == "ir_compiler":
                    error = state.get("error_context", "")
                    if not error:
                        style, msg = _NODE_COMPLETE_LABELS["ir_compiler"]
                        console.print(f"[{style}]✓ {msg}[/{style}]")
                    else:
                        retry = state.get("retry_count", 0)
                        max_r = state.get("max_retries", 3)
                        if verbose:
                            console.print(Panel(
                                error,
                                title=f"[red]✗ Compiler error (attempt {retry}/{max_r})[/red]",
                                border_style="red",
                            ))
                        else:
                            first_line = error.split("\n")[0][:200]
                            console.print(
                                f"[red]✗ Compiler error (attempt {retry}/{max_r}): "
                                f"{first_line}[/red]"
                            )
                            console.print("[dim]   (use --verbose / -v to see full details)[/dim]")
                        console.print("[yellow]   Retrying with error feedback...[/yellow]")

                elif node_name == "solver_runner":
                    solution = state.get("solution")
                    if solution:
                        if solution.error_message:
                            retry = state.get("retry_count", 0)
                            max_r = state.get("max_retries", 3)
                            if verbose:
                                detail = solution.error_message
                                if solution.solver_output:
                                    detail += f"\n\nSolver output:\n{solution.solver_output}"
                                console.print(Panel(
                                    detail,
                                    title=f"[red]✗ Solver error (attempt {retry}/{max_r})[/red]",
                                    border_style="red",
                                ))
                            else:
                                console.print(
                                    f"[red]✗ Solver error (attempt {retry}/{max_r}): "
                                    f"{solution.error_message[:200]}[/red]"
                                )
                                console.print("[dim]   (use --verbose / -v to see full details)[/dim]")
                            console.print("[yellow]   Retrying with error feedback...[/yellow]")
                        else:
                            style, msg = _NODE_COMPLETE_LABELS["solver_runner"]
                            console.print(f"[{style}]✓ {msg}[/{style}]")

        # Save debug artifacts when output_dir is set
        if output_dir_str:
            _last_saved_code = _save_artifacts(state, output_dir_str, _last_saved_code, console)

        # Check if we have a final report
        if state.get("report"):
            # Save solution outputs
            if output_dir_str:
                _save_solution(state, output_dir_str, console)

            console.print()
            console.print(Panel(
                Markdown(state["report"]),
                title="Solution Report",
                border_style="green",
            ))

            # Show solution details
            solution = state.get("solution")
            if solution:
                console.print(f"\nStatus: {solution.status.value}")
                if solution.objective_value is not None:
                    console.print(f"Objective Value: {solution.objective_value}")
                if solution.solve_time_seconds is not None:
                    console.print(f"Solve Time: {solution.solve_time_seconds:.2f}s")
            break

        # If needs user input, prompt
        if state.get("needs_user_input"):
            # Show the last assistant message
            messages = state.get("messages", [])
            if messages and messages[-1]["role"] == "assistant":
                console.print()
                console.print(Markdown(messages[-1]["content"]))
                console.print()

            user_input = console.input("[bold blue]You:[/bold blue] ")
            if user_input.strip().lower() in ("quit", "exit", "q"):
                console.print("Goodbye!")
                raise typer.Exit()

            state["messages"].append({"role": "user", "content": user_input})
            state["needs_user_input"] = False


@app.command()
def config() -> None:
    """Show current configuration."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    console.print(Panel("ORPilot Configuration", border_style="blue"))
    console.print(f"LLM Provider: {os.getenv('ORPILOT_LLM_PROVIDER', 'openai')}")
    console.print(f"Model: {os.getenv('ORPILOT_MODEL', '(default)')}")
    console.print(f"Default Solver: {os.getenv('ORPILOT_DEFAULT_SOLVER', 'pulp')}")
    console.print(f"OpenAI Key: {'set' if os.getenv('OPENAI_API_KEY') else 'not set'}")
    console.print(f"Anthropic Key: {'set' if os.getenv('ANTHROPIC_API_KEY') else 'not set'}")


if __name__ == "__main__":
    app()
