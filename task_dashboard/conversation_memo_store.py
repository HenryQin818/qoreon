from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _safe_text(value: Any, max_len: int) -> str:
    txt = "" if value is None else str(value)
    if len(txt) > max_len:
        return txt[: max_len - 1] + "…"
    return txt


class ConversationMemoStore:
    """Persistent memo storage keyed by (project_id, session_id)."""

    def __init__(
        self,
        base_dir: Path,
        *,
        max_items_per_session: int = 200,
        max_text_len: int = 20_000,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_items_per_session = max(1, min(int(max_items_per_session), 1000))
        self.max_text_len = max(500, min(int(max_text_len), 100_000))
        self._lock = threading.Lock()

    def _sanitize_segment(self, value: Any, *, fallback: str) -> str:
        txt = _safe_text(value, 160).strip()
        if not txt:
            return fallback
        out_chars: list[str] = []
        for ch in txt:
            if ch.isalnum() or ch in {"-", "_", "."}:
                out_chars.append(ch)
            else:
                out_chars.append("_")
        normalized = "".join(out_chars).strip("_")
        return normalized or fallback

    def _memo_path(self, project_id: str, session_id: str) -> Path:
        pid = self._sanitize_segment(project_id, fallback="unknown_project")
        sid = self._sanitize_segment(session_id, fallback="unknown_session")
        return self.base_dir / pid / (sid + ".json")

    def _normalize_attachment(self, raw: Any) -> dict[str, str] | None:
        if not isinstance(raw, dict):
            return None
        filename = _safe_text(raw.get("filename"), 260).strip()
        original_name = _safe_text(raw.get("originalName") or raw.get("original_name") or filename, 260).strip()
        url = _safe_text(raw.get("url"), 2200).strip()
        data_url = _safe_text(raw.get("dataUrl") or raw.get("data_url"), 2200).strip()
        if not filename and not url and not data_url:
            return None
        # Memo store keeps lightweight link fields only.
        return {
            "filename": filename,
            "originalName": original_name,
            "url": url or data_url,
        }

    def _normalize_item(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        item_id = _safe_text(raw.get("id"), 80).strip()
        if not item_id:
            return None
        text = _safe_text(raw.get("text") or raw.get("message"), self.max_text_len).strip()
        attachments: list[dict[str, str]] = []
        for att in (raw.get("attachments") if isinstance(raw.get("attachments"), list) else []):
            norm = self._normalize_attachment(att)
            if norm:
                attachments.append(norm)
        created_at = _safe_text(raw.get("createdAt"), 80).strip() or _now_iso()
        updated_at = _safe_text(raw.get("updatedAt"), 80).strip() or created_at
        return {
            "id": item_id,
            "text": text,
            "attachments": attachments,
            "createdAt": created_at,
            "updatedAt": updated_at,
        }

    def _default_state(self, project_id: str, session_id: str) -> dict[str, Any]:
        return {
            "version": "v1",
            "projectId": str(project_id),
            "sessionId": str(session_id),
            "updatedAt": "",
            "items": [],
        }

    def _load_state(self, project_id: str, session_id: str) -> dict[str, Any]:
        path = self._memo_path(project_id, session_id)
        if not path.exists():
            return self._default_state(project_id, session_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state(project_id, session_id)
        if not isinstance(data, dict):
            return self._default_state(project_id, session_id)
        state = self._default_state(project_id, session_id)
        state["updatedAt"] = _safe_text(data.get("updatedAt"), 80).strip()
        rows = data.get("items") if isinstance(data.get("items"), list) else []
        items: list[dict[str, Any]] = []
        for row in rows:
            item = self._normalize_item(row)
            if item:
                items.append(item)
        state["items"] = items[: self.max_items_per_session]
        return state

    def _save_state(self, project_id: str, session_id: str, state: dict[str, Any]) -> None:
        path = self._memo_path(project_id, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "v1",
            "projectId": str(project_id),
            "sessionId": str(session_id),
            "updatedAt": _safe_text(state.get("updatedAt"), 80).strip(),
            "items": state.get("items") if isinstance(state.get("items"), list) else [],
        }
        tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(4)}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def list(self, project_id: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._load_state(project_id, session_id)
            items = list(state.get("items") or [])
            return {
                "projectId": str(project_id),
                "sessionId": str(session_id),
                "count": len(items),
                "updatedAt": _safe_text(state.get("updatedAt"), 80).strip(),
                "items": items,
            }

    def create(
        self,
        project_id: str,
        session_id: str,
        *,
        text: Any,
        attachments: Any,
    ) -> tuple[dict[str, Any], int]:
        clean_text = _safe_text(text, self.max_text_len).strip()
        normalized_attachments: list[dict[str, str]] = []
        for att in (attachments if isinstance(attachments, list) else []):
            norm = self._normalize_attachment(att)
            if norm:
                normalized_attachments.append(norm)
        if not clean_text and not normalized_attachments:
            raise ValueError("empty memo")

        with self._lock:
            state = self._load_state(project_id, session_id)
            now = _now_iso()
            item = {
                "id": "memo_" + secrets.token_hex(8),
                "text": clean_text,
                "attachments": normalized_attachments,
                "createdAt": now,
                "updatedAt": now,
            }
            items = [item]
            items.extend(list(state.get("items") or []))
            state["items"] = items[: self.max_items_per_session]
            state["updatedAt"] = now
            self._save_state(project_id, session_id, state)
            return item, len(state["items"])

    def delete(self, project_id: str, session_id: str, ids: list[str]) -> tuple[int, int]:
        want = {str(x).strip() for x in (ids or []) if str(x).strip()}
        if not want:
            return 0, self.list(project_id, session_id).get("count", 0)

        with self._lock:
            state = self._load_state(project_id, session_id)
            old_items = list(state.get("items") or [])
            new_items = [it for it in old_items if str(it.get("id") or "") not in want]
            deleted = max(0, len(old_items) - len(new_items))
            if deleted > 0:
                state["items"] = new_items
                state["updatedAt"] = _now_iso()
                self._save_state(project_id, session_id, state)
            return deleted, len(new_items)

    def clear(self, project_id: str, session_id: str) -> int:
        with self._lock:
            state = self._load_state(project_id, session_id)
            old_count = len(list(state.get("items") or []))
            if old_count > 0:
                state["items"] = []
                state["updatedAt"] = _now_iso()
                self._save_state(project_id, session_id, state)
            return old_count
