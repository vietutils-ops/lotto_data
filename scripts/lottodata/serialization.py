"""Deterministic JSON serialization and safe file IO.

Checksums are computed over exact file bytes, so the serialized form must be a
pure function of the content: fixed key order, fixed separators, UTF-8, LF line
endings and a trailing newline. Each draw occupies exactly one line, which keeps
git diffs readable (a new draw adds one line).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .errors import LottoDataError
from .models import Dataset

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class JsonFileError(LottoDataError):
    """Raised when a file cannot be read or is not valid JSON."""

    code = "file_unreadable"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("naive datetime; use an aware UTC datetime")
    return moment.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)


def utc_now_iso() -> str:
    return format_utc(utc_now())


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def _compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def dumps_draws(dataset: Dataset) -> bytes:
    """Canonical ``draws.json``: fixed key order, one draw per line."""
    lines = [
        "{",
        f'  "schema_version": {json.dumps(SCHEMA_VERSION)},',
        f'  "game_code": {json.dumps(dataset.game_code)},',
        f'  "country_code": {json.dumps(dataset.country_code)},',
        f'  "operator_code": {json.dumps(dataset.operator_code)},',
        f'  "dataset_version": {json.dumps(dataset.dataset_version)},',
        f'  "updated_at": {json.dumps(dataset.updated_at)},',
        f'  "draw_count": {json.dumps(dataset.draw_count)},',
    ]
    if not dataset.draws:
        lines.append('  "draws": []')
    else:
        lines.append('  "draws": [')
        last = len(dataset.draws) - 1
        for index, draw in enumerate(dataset.draws):
            suffix = "," if index < last else ""
            lines.append(f"    {_compact(draw.to_record())}{suffix}")
        lines.append("  ]")
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def dumps_json(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temp file in the same directory, then rename (atomic on POSIX)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp creates 0600 files; published files must be readable like any other.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp_name, 0o644 & ~umask)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_bytes(path: Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise JsonFileError(f"{path}: cannot read file ({exc.strerror or exc})") from exc


def loads_json(data: bytes, source: str = "<bytes>") -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonFileError(f"{source}: not valid UTF-8 ({exc})") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonFileError(
            f"{source}: malformed JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc


def read_json_file(path: Path) -> Any:
    return loads_json(read_bytes(path), str(path))
