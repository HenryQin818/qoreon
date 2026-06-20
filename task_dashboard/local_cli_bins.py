from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from task_dashboard.config import resolve_dashboard_local_config_path

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

CLI_BIN_KEY_ORDER = ["codex", "claude", "opencode", "gemini", "trae_cli", "codebuddy"]
CLI_BIN_KEY_LABELS = {
    "codex": "codex",
    "claude": "claude",
    "opencode": "opencode",
    "gemini": "gemini",
    "trae_cli": "trae-cli",
    "codebuddy": "codebuddy",
}


def default_script_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def normalize_cli_bin_key(value: Any) -> str:
    txt = str(value or "").strip().lower().replace("-", "_")
    if txt == "trae":
        return "trae_cli"
    if txt in CLI_BIN_KEY_LABELS:
        return txt
    return ""


def cli_bin_command_name(value: Any) -> str:
    key = normalize_cli_bin_key(value)
    return CLI_BIN_KEY_LABELS.get(key, str(value or "").strip())


def _local_config_path(script_dir: Optional[Path] = None) -> Path:
    base = (script_dir or default_script_dir()).resolve()
    return resolve_dashboard_local_config_path(base)


def load_local_cli_bin_overrides(script_dir: Optional[Path] = None) -> dict[str, str]:
    path = _local_config_path(script_dir)
    if tomllib is None or not path.exists():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    runtime = raw.get("runtime") if isinstance(raw, dict) else {}
    cli_bins = runtime.get("cli_bins") if isinstance(runtime, dict) else {}
    if not isinstance(cli_bins, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in cli_bins.items():
        norm = normalize_cli_bin_key(key)
        if not norm:
            continue
        txt = str(value or "").strip()
        if not txt:
            continue
        out[norm] = txt
    return out


def get_local_cli_bin_override(command_or_key: Any, script_dir: Optional[Path] = None) -> str:
    key = normalize_cli_bin_key(command_or_key)
    if not key:
        return ""
    return str(load_local_cli_bin_overrides(script_dir).get(key) or "").strip()


def _toml_string(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def set_runtime_cli_bins_in_config_text(config_content: str, patch: dict[str, Any]) -> str:
    content = str(config_content or "")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in (patch or {}).items():
        key = normalize_cli_bin_key(raw_key)
        if not key:
            continue
        txt = str(raw_value or "").strip()
        if txt:
            normalized[key] = txt

    section_lines = ["[runtime.cli_bins]"]
    for key in CLI_BIN_KEY_ORDER:
        value = normalized.get(key)
        if value:
            section_lines.append(f"{key} = {_toml_string(value)}")
    section_text = "\n".join(section_lines) + "\n" if len(section_lines) > 1 else ""

    pattern = re.compile(r"(?ms)^\[runtime\.cli_bins\]\s*$\n?(.*?)(?=^\[|\Z)")
    match = pattern.search(content)
    if match:
        if section_text:
            updated = content[: match.start()] + section_text + content[match.end() :]
        else:
            updated = content[: match.start()] + content[match.end() :]
    else:
        if not section_text:
            updated = content
        else:
            suffix = "" if not content.strip() else ("\n\n" if not content.endswith("\n") else "\n")
            updated = content + suffix + section_text

    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated.lstrip("\n")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_local_cli_bin_overrides(patch: dict[str, Any], script_dir: Optional[Path] = None) -> Path:
    path = _local_config_path(script_dir)
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = set_runtime_cli_bins_in_config_text(raw, patch)
    _atomic_write_text(path, updated)
    return path
