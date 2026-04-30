from __future__ import annotations

import ipaddress
import json
import time
from pathlib import Path
from typing import Any

from task_dashboard.helpers import atomic_write_text


SCHEMA_VERSION = "platform_lan_access.v1"
CONFIG_REL_PATH = Path(".run") / "platform-lan-access.json"
LOCAL_ONLY_BIND = "127.0.0.1"
LAN_BIND = "0.0.0.0"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def config_path(runtime_base_dir: Path) -> Path:
    return Path(runtime_base_dir).expanduser().resolve() / CONFIG_REL_PATH


def normalize_host(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    if "%" in text:
        text = text.split("%", 1)[0]
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return text.lower()
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return str(ip)


def client_host(client_address: Any) -> str:
    if isinstance(client_address, (tuple, list)) and client_address:
        return normalize_host(client_address[0])
    return normalize_host(client_address)


def load_config(runtime_base_dir: Path) -> dict[str, Any]:
    path = config_path(runtime_base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "schemaVersion": str(data.get("schemaVersion") or SCHEMA_VERSION),
        "enabled": bool(data.get("enabled")),
        "updatedAt": str(data.get("updatedAt") or ""),
        "updatedBy": str(data.get("updatedBy") or ""),
    }


def save_config(runtime_base_dir: Path, *, enabled: bool, updated_by: str = "") -> dict[str, Any]:
    path = config_path(runtime_base_dir)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "enabled": bool(enabled),
        "updatedAt": now_iso(),
        "updatedBy": str(updated_by or "").strip(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def desired_bind(enabled: bool) -> str:
    return LAN_BIND if enabled else LOCAL_ONLY_BIND


def is_loopback_bind(bind_host: Any) -> bool:
    host = normalize_host(bind_host)
    if not host or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def bind_exposes_lan(bind_host: Any) -> bool:
    host = normalize_host(bind_host)
    if host in {LAN_BIND, "::"}:
        return True
    if not host or host == "localhost":
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not ip.is_loopback


def _private_ip(value: Any) -> ipaddress._BaseAddress | None:
    host = normalize_host(value)
    if not host:
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip.is_loopback or ip.is_link_local or not ip.is_private:
        return None
    return ip


def is_trusted_lan_client_address(
    client_address: Any,
    *,
    local_addresses: set[str] | None = None,
) -> bool:
    client_ip = _private_ip(client_host(client_address))
    if client_ip is None:
        return False
    local_private_ips = [
        ip
        for ip in (_private_ip(item) for item in (local_addresses or set()))
        if ip is not None and ip.version == client_ip.version
    ]
    if not local_private_ips:
        return False
    for local_ip in local_private_ips:
        if client_ip.version == 4:
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
            if client_ip in network:
                return True
        elif client_ip.version == 6:
            network = ipaddress.ip_network(f"{local_ip}/64", strict=False)
            if client_ip in network:
                return True
    return False


def build_state(
    *,
    runtime_base_dir: Path,
    current_bind: str,
    port: int,
    local_origin: str = "",
    public_origin: str = "",
    local_addresses: set[str] | None = None,
) -> dict[str, Any]:
    cfg = load_config(runtime_base_dir)
    enabled = bool(cfg.get("enabled"))
    desired = desired_bind(enabled)
    current = normalize_host(current_bind) or str(current_bind or "")
    if enabled:
        bind_ready = bind_exposes_lan(current)
        restart_reason = "" if bind_ready else "enable_requires_bind_0_0_0_0"
    else:
        bind_ready = is_loopback_bind(current)
        restart_reason = "" if bind_ready else "disable_requires_bind_127_0_0_1"
    requires_restart = not bind_ready
    effective_enabled = bool(enabled and bind_exposes_lan(current))
    config_file = config_path(runtime_base_dir)
    lan_url = str(public_origin or "").strip()
    local_url = str(local_origin or "").strip()
    return {
        "ok": True,
        "schemaVersion": SCHEMA_VERSION,
        "enabled": enabled,
        "effectiveEnabled": effective_enabled,
        "mode": "trusted_lan_full_access" if enabled else "local_only",
        "networkScope": "trusted_lan_full_access" if effective_enabled else "local_only",
        "remotePolicy": (
            "full_platform_for_trusted_lan"
            if effective_enabled
            else "share_only_allowlist_or_localhost"
        ),
        "requiresRestart": requires_restart,
        "requires_restart": requires_restart,
        "restartReason": restart_reason,
        "runtimeConfig": {
            "path": str(config_file),
            "exists": config_file.exists(),
            "updatedAt": str(cfg.get("updatedAt") or ""),
            "updatedBy": str(cfg.get("updatedBy") or ""),
        },
        "listen": {
            "currentBind": current,
            "desiredBind": desired,
            "port": int(port or 0),
            "requiresRestart": requires_restart,
            "restartReason": restart_reason,
        },
        "origins": {
            "localOrigin": local_url,
            "publicOrigin": lan_url,
            "lanUrl": lan_url,
        },
        "lan": {
            "url": lan_url,
            "localAddresses": sorted(str(item) for item in (local_addresses or set())),
        },
        "frontEndAction": {
            "showRequiresRestart": requires_restart,
            "restartHint": (
                "重启 task-dashboard 服务后监听地址才会切换。"
                if requires_restart
                else ""
            ),
        },
    }


def update_response(
    *,
    runtime_base_dir: Path,
    payload: dict[str, Any],
    current_bind: str,
    port: int,
    local_origin: str = "",
    public_origin: str = "",
    local_addresses: set[str] | None = None,
    updated_by: str = "",
) -> tuple[int, dict[str, Any]]:
    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "bad json"}
    raw = payload.get("enabled") if "enabled" in payload else payload.get("platformLanAccessEnabled")
    if raw is None:
        return 400, {"ok": False, "error": "missing enabled"}
    if isinstance(raw, bool):
        enabled = raw
    elif isinstance(raw, (int, float)):
        enabled = bool(raw)
    else:
        text = str(raw or "").strip().lower()
        if text in {"1", "true", "yes", "on", "enabled"}:
            enabled = True
        elif text in {"0", "false", "no", "off", "disabled"}:
            enabled = False
        else:
            return 400, {"ok": False, "error": "invalid enabled"}
    save_config(runtime_base_dir, enabled=enabled, updated_by=updated_by)
    return 200, build_state(
        runtime_base_dir=runtime_base_dir,
        current_bind=current_bind,
        port=port,
        local_origin=local_origin,
        public_origin=public_origin,
        local_addresses=local_addresses,
    )
