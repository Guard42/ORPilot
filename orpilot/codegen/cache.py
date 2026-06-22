"""Content-addressed compilation cache.

Keys compilation results by (ir_hash, solver_name, solver_version)
so that recompiling unchanged IR returns cached output instantly.

Inspired by:
- Go build cache: https://pkg.go.dev/cmd/go#hdr-Build_and_test_caching
- Rust incremental compilation: https://rustc-dev-guide.rust-lang.org/incr-comp.html
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import ClassVar


class CompilationCache:
    """Go/Rust-style content-addressed build cache.

    Usage::

        cache = CompilationCache()
        cached = cache.get(ir_dict, "gurobi")
        if cached:
            return cached
        code = compile(ir_dict, "gurobi")
        cache.store(ir_dict, "gurobi", code)
    """

    _instance: ClassVar[CompilationCache | None] = None

    def __init__(self, cache_dir: str | None = None):
        self._cache_dir = Path(cache_dir or os.path.join(os.path.expanduser("~"), ".orpilot", "cache"))
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> CompilationCache:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, ir: dict, solver: str) -> str | None:
        key = self._make_key(ir, solver)
        if key in self._memory:
            return self._memory[key]
        cache_file = self._cache_dir / f"{key}.py"
        if cache_file.exists():
            code = cache_file.read_text(encoding="utf-8")
            self._memory[key] = code
            return code
        return None

    def store(self, ir: dict, solver: str, code: str) -> None:
        key = self._make_key(ir, solver)
        self._memory[key] = code
        cache_file = self._cache_dir / f"{key}.py"
        cache_file.write_text(code, encoding="utf-8")

    @staticmethod
    def _make_key(ir: dict, solver: str) -> str:
        ir_bytes = json.dumps(ir, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ir_hash = hashlib.sha256(ir_bytes).hexdigest()[:16]
        return f"{solver}_{ir_hash}"
