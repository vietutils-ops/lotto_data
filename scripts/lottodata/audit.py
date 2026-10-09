"""Append-only audit log (metadata/audit_log.jsonl): one JSON object per line."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping

from . import TOOL_NAME, TOOL_VERSION
from .layout import RepoLayout


def append_event(layout: RepoLayout, event: Mapping[str, Any]) -> Dict[str, Any]:
    """Appends ``event`` (with the tool version) and returns what was written."""
    record = {"tool": f"{TOOL_NAME}/{TOOL_VERSION}", **event}
    if "at" not in record or "action" not in record:
        raise ValueError("audit events need 'at' and 'action'")
    layout.audit_log.parent.mkdir(parents=True, exist_ok=True)
    with open(layout.audit_log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def read_events(layout: RepoLayout) -> List[Dict[str, Any]]:
    if not layout.audit_log.is_file():
        return []
    with open(layout.audit_log, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
