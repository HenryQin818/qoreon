from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_MODEL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def audit_session_model_integrity(
    *,
    base_dir: Path,
    max_detail_items: int = 100,
) -> dict[str, Any]:
    sessions_dir = base_dir / ".sessions"
    checked_sessions = 0
    pass_count = 0
    missing_count = 0
    invalid_count = 0
    missing_items: list[dict[str, str]] = []
    invalid_items: list[dict[str, str]] = []
    by_cli: dict[str, int] = {}

    if not sessions_dir.exists():
        return {
            "checked_sessions": 0,
            "pass_count": 0,
            "missing_count": 0,
            "invalid_count": 0,
            "by_cli": {},
            "missing_items": [],
            "invalid_items": [],
        }

    for p in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        arr = data.get("sessions")
        if not isinstance(arr, list):
            continue
        for row in arr:
            if not isinstance(row, dict):
                continue
            checked_sessions += 1
            sid = _safe_text(row.get("id"))
            cli_type = _safe_text(row.get("cli_type")).lower() or "codex"
            model = _safe_text(row.get("model"))
            by_cli[cli_type] = int(by_cli.get(cli_type) or 0) + 1

            if not model:
                missing_count += 1
                if len(missing_items) < max_detail_items:
                    missing_items.append(
                        {"session_id": sid, "cli_type": cli_type, "path": str(p), "reason": "empty_model"}
                    )
                continue

            if not _MODEL_RE.match(model):
                invalid_count += 1
                if len(invalid_items) < max_detail_items:
                    invalid_items.append(
                        {"session_id": sid, "cli_type": cli_type, "path": str(p), "reason": "invalid_model_format"}
                    )
                continue

            pass_count += 1

    return {
        "checked_sessions": checked_sessions,
        "pass_count": pass_count,
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "by_cli": by_cli,
        "missing_items": missing_items,
        "invalid_items": invalid_items,
    }

