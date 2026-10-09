"""SHA-256 checksums in the standard ``sha256sum`` format.

``checksums/SHA256SUMS`` can be verified with ``sha256sum -c checksums/SHA256SUMS``
from the repository root.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .layout import RepoLayout
from .serialization import atomic_write_bytes

_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


class ChecksumFileError(ValueError):
    pass


@dataclass(frozen=True)
class ChecksumProblem:
    path: str
    problem: str  # mismatch | missing_file | unlisted_file

    def render(self) -> str:
        return f"{self.path}: {self.problem}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_sums(entries: Dict[str, str]) -> bytes:
    lines = [f"{digest}  {path}" for path, digest in sorted(entries.items())]
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def parse_sums(text: str) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        match = _LINE.match(line)
        if not match:
            raise ChecksumFileError(f"SHA256SUMS line {line_no} is malformed: {line!r}")
        digest, path = match.groups()
        if path in entries:
            raise ChecksumFileError(f"SHA256SUMS lists {path} twice")
        entries[path] = digest
    return entries


def compute_entries(layout: RepoLayout) -> Dict[str, str]:
    return {layout.relative(path): sha256_file(path) for path in layout.published_files()}


def write_checksums(layout: RepoLayout) -> Dict[str, str]:
    entries = compute_entries(layout)
    atomic_write_bytes(layout.checksums_file, render_sums(entries))
    return entries


def verify_checksums(layout: RepoLayout) -> List[ChecksumProblem]:
    if not layout.checksums_file.is_file():
        return [ChecksumProblem("checksums/SHA256SUMS", "missing_file")]
    listed = parse_sums(layout.checksums_file.read_text(encoding="utf-8"))
    problems: List[ChecksumProblem] = []
    for rel, digest in sorted(listed.items()):
        path = layout.root / rel
        if not path.is_file():
            problems.append(ChecksumProblem(rel, "missing_file"))
        elif sha256_file(path) != digest:
            problems.append(ChecksumProblem(rel, "mismatch"))
    for path in layout.published_files():
        rel = layout.relative(path)
        if rel not in listed:
            problems.append(ChecksumProblem(rel, "unlisted_file"))
    return problems
