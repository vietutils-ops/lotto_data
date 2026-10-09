"""JSON Schema validation of the repository's files (schemas/*.schema.json)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, List

from .layout import RepoLayout
from .serialization import read_json_file


@lru_cache(maxsize=None)
def _validator(schemas_dir: str, name: str):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("jsonschema is required: pip install -r requirements.txt") from exc
    schema = read_json_file(Path(schemas_dir) / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_problems(layout: RepoLayout, document: Any, name: str) -> List[str]:
    """Problems of [document] against ``schemas/<name>.schema.json`` (empty when valid)."""
    validator = _validator(str(layout.schemas_dir), name)
    problems = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in error.absolute_path) or "(root)"
        problems.append(f"{where}: {error.message}")
        if len(problems) >= 10:
            break
    return problems
