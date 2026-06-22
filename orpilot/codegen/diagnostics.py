"""Diagnostics engine with source location tracking.

Produces Rust-style structured error messages with file/line/column
context, help text, and notes.

Inspired by:
- Rustc diagnostics: https://rustc-dev-guide.rust-lang.org/diagnostics.html
- LLVM SourceMgr: https://llvm.org/doxygen/classllvm_1_1SourceMgr.html
- Clang diagnostics: https://clang.llvm.org/docs/InternalsManual.html#the-diagnostics-subsystem
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SourceLocation:
    """LLVM-style source location in a JSON file."""
    file: str = "ir.json"
    line: int = 1
    column: int = 1
    snippet: str = ""


@dataclass
class Diagnostic:
    """Rust-style diagnostic with severity, location, and help."""
    level: Literal["error", "warning", "note", "help"]
    code: str           # e.g., "E003"
    message: str
    location: SourceLocation | None = None
    help_text: str | None = None
    notes: list[str] = field(default_factory=list)

    def format(self) -> str:
        """Format the diagnostic as a Rust-style error message."""
        parts = [f"{self.level}[{self.code}]: {self.message}"]
        if self.location:
            parts.append(f"  --> {self.location.file}:{self.location.line}:{self.location.column}")
            parts.append("   |")
            parts.append(f"{self.location.line:3} | {self.location.snippet}")
            underline = " " * (self.location.column - 1) + "^" + "~" * (len(self.location.snippet.split(":")[0].strip()) - self.location.column + 1) if self.location.snippet else "   ^"
            parts.append(f"   | {underline}")
        if self.help_text:
            parts.append(f"   = help: {self.help_text}")
        for note in self.notes:
            parts.append(f"   = note: {note}")
        return "\n".join(parts)


class DiagnosticEngine:
    """Collects and formats diagnostics during compilation."""

    def __init__(self):
        self.diagnostics: list[Diagnostic] = []
        self._error_count = 0
        self._warning_count = 0

    def error(self, code: str, message: str, location: SourceLocation | None = None,
              help_text: str | None = None, notes: list[str] | None = None) -> None:
        self.diagnostics.append(Diagnostic("error", code, message, location, help_text, notes or []))
        self._error_count += 1

    def warning(self, code: str, message: str, location: SourceLocation | None = None,
                help_text: str | None = None) -> None:
        self.diagnostics.append(Diagnostic("warning", code, message, location, help_text))
        self._warning_count += 1

    @property
    def has_errors(self) -> bool:
        return self._error_count > 0

    @property
    def has_warnings(self) -> bool:
        return self._warning_count > 0

    def format_all(self) -> str:
        return "\n\n".join(d.format() for d in self.diagnostics)

    def raise_if_errors(self) -> None:
        if self.has_errors:
            raise ValueError(
                f"Compilation failed with {self._error_count} error(s):\n"
                f"{self.format_all()}"
            )


# ---------------------------------------------------------------------------
# Helpers for JSON source location tracking
# ---------------------------------------------------------------------------

def locate_in_json(ir: dict, key_path: list[str], default_file: str = "ir.json") -> SourceLocation:
    """Find the approximate source location of a key in an IR JSON.

    This is a best-effort heuristic — without a real JSON parser that tracks
    positions, we approximate by key name lookup.
    """
    current: dict = ir
    for i, key in enumerate(key_path[:-1]):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            break

    last_key = key_path[-1] if key_path else "?"
    snippet = json.dumps(current.get(last_key, "?"))[:80] if isinstance(current, dict) else "?"

    return SourceLocation(file=default_file, snippet=snippet)


def diagnose_missing_field(ir: dict, section: str, key: str, field: str,
                           help_text: str) -> None:
    """Quick helper for the most common diagnostic: missing required field."""
    eng = DiagnosticEngine()
    eng.error(
        code="E001",
        message=f"In '{section}.{key}': missing required field '{field}'",
        help_text=help_text,
    )
    eng.raise_if_errors()


import json
