"""Mutation audit logging — every write operation is logged locally."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log_mutation(
    log_file: str,
    *,
    operation: str,
    customer_id: str = "",
    entity_type: str = "",
    entity_id: str = "",
    changes: dict[str, Any] | None = None,
    dry_run: bool = True,
    result: str = "success",
    error: str = "",
    previous_state: dict[str, Any] | None = None,
) -> str:
    """Append a mutation record to the audit log file.

    Returns the ``entry_id`` assigned to this record.
    """
    path = Path(log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    entry_id = str(uuid.uuid4())

    record: dict[str, Any] = {
        "entry_id": entry_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "customer_id": customer_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "changes": changes or {},
        "dry_run": dry_run,
        "result": result,
        "error": error,
    }

    if previous_state is not None:
        record["previous_state"] = previous_state

    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")

    return entry_id


# ---------------------------------------------------------------------------
# Audit log readers
# ---------------------------------------------------------------------------


def read_recent_mutations(log_file: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent *limit* non-dry-run mutation entries.

    Reads the JSONL audit log and returns entries in reverse-chronological
    order (newest first). Skips dry-run entries since those made no changes.
    """
    path = Path(log_file).expanduser()
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("dry_run", True):
                continue
            entries.append(record)

    # Return newest first, capped at limit
    return entries[-limit:][::-1]


def get_mutation_by_id(
    log_file: str, entry_id: str
) -> dict[str, Any] | None:
    """Find a single audit log entry by its ``entry_id``."""
    path = Path(log_file).expanduser()
    if not path.exists():
        return None

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("entry_id") == entry_id:
                return record

    return None
