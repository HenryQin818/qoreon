from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from task_dashboard.runtime.session_directory_snapshot import session_directory_snapshot_diagnostics


_HTTP_LOG_RE = re.compile(
    r'^\S+\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+"(?P<method>[A-Z]+)\s+(?P<url>\S+)\s+HTTP/[^"]+"\s+(?P<status>\d{3})'
)
_SWAP_RE = re.compile(
    r"total = (?P<total>[\d.]+)(?P<total_unit>[KMGTP])\s+used = (?P<used>[\d.]+)(?P<used_unit>[KMGTP])\s+free = (?P<free>[\d.]+)(?P<free_unit>[KMGTP])"
)
_VM_STAT_RE = re.compile(r"^(?P<label>[^:]+):\s+(?P<value>[\d.]+)\.$")
_PAGE_SIZE_RE = re.compile(r"page size of (?P<size>\d+) bytes")
_DYNAMIC_ID_RE = re.compile(r"^[0-9a-f]{8,}[-0-9a-f]*$", re.IGNORECASE)

_CACHE_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SNAPSHOT_REFRESH_INFLIGHT: dict[str, threading.Event] = {}

_HOT_ENDPOINT_PREFIXES = (
    "/api/conversation-memos",
    "/api/codex/runs",
    "/api/codex/run/:id",
    "/api/sessions",
    "/api/sessions/:id",
    "/api/projects/:project_id/auto-scheduler",
    "/api/projects/:project_id/auto-scheduler/inspection-tasks",
    "/api/projects/:project_id/heartbeat-tasks",
)


def _perf_snapshot_cache_key(*, environment_name: str, port: int, project_id: str, pid: int) -> str:
    return f"{environment_name}:{port}:{project_id}:{pid}"


def _store_perf_snapshot_cache(cache_key: str, snapshot: dict[str, Any], *, cached_at: float | None = None) -> None:
    with _CACHE_LOCK:
        _SNAPSHOT_CACHE[cache_key] = (float(cached_at if cached_at is not None else time.time()), dict(snapshot))


def _start_perf_snapshot_refresh(
    *,
    cache_key: str,
    repo_root: Path,
    environment_name: str,
    port: int,
    project_id: str,
    http_log_path: Path | None,
    current_pid: int | None,
    max_http_log_bytes: int,
) -> bool:
    with _CACHE_LOCK:
        inflight = _SNAPSHOT_REFRESH_INFLIGHT.get(cache_key)
        if inflight is not None and not inflight.is_set():
            return False
        done = threading.Event()
        _SNAPSHOT_REFRESH_INFLIGHT[cache_key] = done

    def _worker() -> None:
        try:
            snapshot = _build_runtime_perf_snapshot_uncached(
                repo_root=repo_root,
                environment_name=environment_name,
                port=port,
                project_id=project_id,
                http_log_path=http_log_path,
                current_pid=current_pid,
                now=None,
                max_http_log_bytes=max_http_log_bytes,
            )
            _store_perf_snapshot_cache(cache_key, snapshot)
        except Exception:
            pass
        finally:
            with _CACHE_LOCK:
                current = _SNAPSHOT_REFRESH_INFLIGHT.get(cache_key)
                if current is done:
                    _SNAPSHOT_REFRESH_INFLIGHT.pop(cache_key, None)
                done.set()

    threading.Thread(
        target=_worker,
        name=f"perf-snapshot-refresh-{port}",
        daemon=True,
    ).start()
    return True


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _fmt_number(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def _fmt_cpu(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def _fmt_gb(value: Any) -> str:
    try:
        return f"{float(value):.1f} GB"
    except Exception:
        return "0.0 GB"


def _fmt_mb(value: Any) -> str:
    try:
        return f"{float(value):.0f} MB"
    except Exception:
        return "0 MB"


def _pct(part: int | float, total: int | float) -> float:
    try:
        if float(total) <= 0:
            return 0.0
        return round((float(part) / float(total)) * 100.0, 1)
    except Exception:
        return 0.0


def _tone(value: float, *, warn: float, danger: float) -> str:
    if value >= danger:
        return "danger"
    if value >= warn:
        return "warn"
    return "good"


def _bytes_from_unit(value_text: str, unit_text: str) -> int:
    unit = unit_text.strip().upper()
    factor_map = {
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
        "P": 1024**5,
    }
    factor = factor_map.get(unit, 1)
    try:
        return int(float(value_text) * factor)
    except Exception:
        return 0


def _run_text(*args: str) -> str:
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return _as_str(proc.stdout).strip()


def _read_tail_text(path: Path, *, max_bytes: int = 6_000_000) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - max_bytes)
            handle.seek(start)
            data = handle.read()
    except Exception:
        return ""
    return data.decode("utf-8", errors="replace")


def _parse_swapusage(text: str) -> dict[str, Any]:
    match = _SWAP_RE.search(text or "")
    if not match:
        return {
            "total_bytes": 0,
            "used_bytes": 0,
            "free_bytes": 0,
            "used_pct": 0.0,
            "used_gb": 0.0,
            "total_gb": 0.0,
        }
    total_bytes = _bytes_from_unit(match.group("total"), match.group("total_unit"))
    used_bytes = _bytes_from_unit(match.group("used"), match.group("used_unit"))
    free_bytes = _bytes_from_unit(match.group("free"), match.group("free_unit"))
    return {
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "used_pct": _pct(used_bytes, total_bytes),
        "used_gb": round(used_bytes / float(1024**3), 2) if total_bytes else 0.0,
        "total_gb": round(total_bytes / float(1024**3), 2) if total_bytes else 0.0,
    }


def _parse_vm_stat(text: str, *, total_bytes: int) -> dict[str, Any]:
    page_size = 4096
    page_match = _PAGE_SIZE_RE.search(text or "")
    if page_match:
        try:
            page_size = max(1, int(page_match.group("size")))
        except Exception:
            page_size = 4096

    page_counts: dict[str, int] = {}
    for raw_line in (text or "").splitlines():
        match = _VM_STAT_RE.match(raw_line.strip())
        if not match:
            continue
        key = match.group("label").strip().lower().replace(" ", "_")
        raw_value = match.group("value").replace(".", "").strip()
        try:
            page_counts[key] = int(raw_value)
        except Exception:
            continue

    free_pages = int(page_counts.get("pages_free") or 0)
    speculative_pages = int(page_counts.get("pages_speculative") or 0)
    active_pages = int(page_counts.get("pages_active") or 0)
    inactive_pages = int(page_counts.get("pages_inactive") or 0)
    wired_pages = int(page_counts.get("pages_wired_down") or 0)
    compressor_pages = int(page_counts.get("pages_occupied_by_compressor") or 0)

    free_bytes = max(0, (free_pages + speculative_pages) * page_size)
    used_bytes = max(0, total_bytes - free_bytes) if total_bytes else 0
    return {
        "page_size_bytes": page_size,
        "free_bytes": free_bytes,
        "used_bytes": used_bytes,
        "used_pct": _pct(used_bytes, total_bytes),
        "active_bytes": active_pages * page_size,
        "inactive_bytes": inactive_pages * page_size,
        "wired_bytes": wired_pages * page_size,
        "compressed_bytes": compressor_pages * page_size,
    }


def _classify_process(args: str, *, pid: int, current_pid: int | None, current_port: int) -> tuple[str, str]:
    lower = args.lower()
    if current_pid is not None and pid == current_pid:
        return "runtime_service", f"stable {current_port}"
    if "windowserver" in lower:
        return "window_server", "WindowServer"
    if (
        "google chrome helper --type=gpu-process" in lower
        or ("chrome-profile" in lower and "--gpu-preferences" in lower)
    ):
        return "chrome_gpu", "Chrome GPU 进程"
    if any(
        token in lower
        for token in (
            "--enable-automation",
            "playwright",
            "chrome-devtools-mcp",
            "ms-playwright",
            ".codex/playwright-profiles",
            ".cache/chrome-devtools-mcp",
            "chrome-profile",
        )
    ):
        return "automation", "自动化浏览器/残留"
    if "google chrome" in lower:
        return "chrome", "Google Chrome"
    if "python" in lower and ".codex" in lower:
        return "codex_residue", "Codex 残留进程"
    label = args.split(" ", 1)[0].strip() or f"PID {pid}"
    return "generic", label


def _short_command(args: str, *, limit: int = 120) -> str:
    text = _as_str(args).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _parse_process_rows(ps_text: str, *, current_pid: int | None, current_port: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in (ps_text or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        try:
            pid = int(parts[0])
            cpu_pct = float(parts[1])
            mem_pct = float(parts[2])
            rss_kb = int(parts[3])
        except Exception:
            continue
        elapsed = parts[4].strip()
        args = parts[5].strip()
        kind, label = _classify_process(args, pid=pid, current_pid=current_pid, current_port=current_port)
        rows.append(
            {
                "pid": pid,
                "cpu_pct": round(cpu_pct, 1),
                "mem_pct": round(mem_pct, 1),
                "rss_kb": rss_kb,
                "rss_mb": round(rss_kb / 1024.0, 1),
                "elapsed": elapsed,
                "kind": kind,
                "label": label,
                "args": args,
                "command": _short_command(args),
                "is_current_runtime": bool(current_pid is not None and pid == current_pid),
            }
        )
    rows.sort(key=lambda row: float(row.get("cpu_pct") or 0.0), reverse=True)
    return rows


def _normalize_endpoint(path: str) -> str:
    clean = _as_str(path).strip() or "/"
    parts = [segment for segment in clean.split("/") if segment]
    if len(parts) >= 4 and parts[:2] == ["api", "codex"] and parts[2] == "run":
        return "/api/codex/run/:id"
    if len(parts) >= 3 and parts[:2] == ["api", "sessions"] and _DYNAMIC_ID_RE.match(parts[2]):
        return "/api/sessions/:id"
    if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
        normalized = [parts[0], parts[1], ":project_id", *parts[3:]]
        return "/" + "/".join(normalized)
    return clean


def _project_from_request(path: str, query: dict[str, list[str]]) -> str:
    for key in ("projectId", "project_id", "project"):
        values = query.get(key) or []
        if values and _as_str(values[0]).strip():
            return _as_str(values[0]).strip()
    parts = [segment for segment in _as_str(path).strip().split("/") if segment]
    if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
        return parts[2]
    return ""


def _session_from_request(path: str, query: dict[str, list[str]]) -> str:
    for key in ("sessionId", "session_id", "session"):
        values = query.get(key) or []
        if values and _as_str(values[0]).strip():
            return _as_str(values[0]).strip()
    parts = [segment for segment in _as_str(path).strip().split("/") if segment]
    if len(parts) >= 3 and parts[:2] == ["api", "sessions"] and _DYNAMIC_ID_RE.match(parts[2]):
        return parts[2]
    return ""


def _parse_http_log_rows(http_log_path: Path | None, *, now: datetime, max_bytes: int) -> list[dict[str, Any]]:
    if http_log_path is None:
        return []
    text = _read_tail_text(http_log_path, max_bytes=max_bytes)
    if not text:
        return []
    rows: list[dict[str, Any]] = []
    earliest = now - timedelta(minutes=60)
    for raw_line in text.splitlines():
        match = _HTTP_LOG_RE.match(raw_line.strip())
        if not match:
            continue
        try:
            created_at = datetime.strptime(match.group("ts"), "%Y-%m-%dT%H:%M:%S%z")
        except Exception:
            continue
        if created_at < earliest:
            continue
        request_url = match.group("url")
        parsed = urlparse(request_url)
        query = parse_qs(parsed.query or "")
        path = parsed.path or "/"
        rows.append(
            {
                "created_at": created_at,
                "method": match.group("method"),
                "status": int(match.group("status")),
                "path": path,
                "endpoint": _normalize_endpoint(path),
                "project_id": _project_from_request(path, query),
                "session_id": _session_from_request(path, query),
            }
        )
    return rows


def _counter_rows(counter: Counter[str], *, total: int, limit: int = 6) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, count in counter.most_common(max(1, int(limit))):
        if not name:
            continue
        out.append(
            {
                "label": name,
                "value": _fmt_number(count),
                "count": int(count),
                "percent": _pct(int(count), total),
            }
        )
    return out


def _window_summary(rows: list[dict[str, Any]], *, now: datetime, minutes: int) -> dict[str, Any]:
    start = now - timedelta(minutes=max(1, int(minutes)))
    subset = [row for row in rows if row.get("created_at") and row["created_at"] >= start]
    endpoint_counts = Counter(_as_str(row.get("endpoint")).strip() for row in subset if _as_str(row.get("endpoint")).strip())
    project_counts = Counter(_as_str(row.get("project_id")).strip() for row in subset if _as_str(row.get("project_id")).strip())
    session_counts = Counter(_as_str(row.get("session_id")).strip() for row in subset if _as_str(row.get("session_id")).strip())
    polling_count = sum(
        count for endpoint, count in endpoint_counts.items() if endpoint.startswith(_HOT_ENDPOINT_PREFIXES)
    )
    error_count = sum(1 for row in subset if int(row.get("status") or 0) >= 400)
    total = len(subset)
    rpm = round(total / float(max(1, minutes)), 1)
    return {
        "minutes": minutes,
        "total_requests": total,
        "requests_per_minute": rpm,
        "error_count": error_count,
        "error_rate_pct": _pct(error_count, total),
        "polling_count": polling_count,
        "polling_rate_pct": _pct(polling_count, total),
        "top_endpoints": _counter_rows(endpoint_counts, total=total, limit=8),
        "top_projects": _counter_rows(project_counts, total=total, limit=8),
        "top_sessions": _counter_rows(session_counts, total=total, limit=8),
    }


def _metric(label: str, value: str, note: str = "") -> dict[str, str]:
    return {"label": label, "value": value, "note": note}


def _build_process_tables(rows: list[dict[str, Any]], *, current_pid: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    chrome_rows = [row for row in rows if row.get("kind") in {"chrome", "chrome_gpu"}]
    automation_rows = [row for row in rows if row.get("kind") in {"automation", "codex_residue"}]
    window_rows = [row for row in rows if row.get("kind") == "window_server"]
    current_row = next((row for row in rows if row.get("is_current_runtime")), None)
    chrome_gpu_row = next((row for row in rows if row.get("kind") == "chrome_gpu"), None)

    chrome_cpu_pct = round(sum(float(row.get("cpu_pct") or 0.0) for row in chrome_rows), 1)
    automation_cpu_pct = round(sum(float(row.get("cpu_pct") or 0.0) for row in automation_rows), 1)
    window_cpu_pct = round(sum(float(row.get("cpu_pct") or 0.0) for row in window_rows), 1)
    current_runtime_cpu_pct = float((current_row or {}).get("cpu_pct") or 0.0)
    current_runtime_rss_mb = float((current_row or {}).get("rss_mb") or 0.0)

    table_rows = [
        {
            "label": _as_str(row.get("label")).strip() or f"PID {row.get('pid')}",
            "pid": int(row.get("pid") or 0),
            "value": _fmt_cpu(row.get("cpu_pct")),
            "count": float(row.get("cpu_pct") or 0.0),
            "note": f"{_fmt_mb(row.get('rss_mb'))} · {row.get('elapsed') or '-'}",
            "command": _as_str(row.get("command")).strip(),
        }
        for row in rows[:10]
    ]
    automation_table = [
        {
            "label": _as_str(row.get("label")).strip() or f"PID {row.get('pid')}",
            "pid": int(row.get("pid") or 0),
            "value": _fmt_cpu(row.get("cpu_pct")),
            "count": float(row.get("cpu_pct") or 0.0),
            "note": f"{_fmt_mb(row.get('rss_mb'))} · {row.get('elapsed') or '-'}",
            "command": _as_str(row.get("command")).strip(),
        }
        for row in automation_rows[:8]
    ]
    summary = {
        "chrome_cpu_pct": chrome_cpu_pct,
        "chrome_gpu_cpu_pct": float((chrome_gpu_row or {}).get("cpu_pct") or 0.0),
        "window_server_cpu_pct": window_cpu_pct,
        "automation_cpu_pct": automation_cpu_pct,
        "automation_count": len(automation_rows),
        "current_runtime_cpu_pct": round(current_runtime_cpu_pct, 1),
        "current_runtime_rss_mb": round(current_runtime_rss_mb, 1),
        "current_runtime_elapsed": _as_str((current_row or {}).get("elapsed")).strip(),
        "current_runtime_pid": int((current_row or {}).get("pid") or (current_pid or 0)),
    }
    return table_rows, automation_table, summary


def _build_diagnosis(
    *,
    request_15m: dict[str, Any],
    process_summary: dict[str, Any],
    swap: dict[str, Any],
    memory: dict[str, Any],
) -> dict[str, Any]:
    chrome_cpu = float(process_summary.get("chrome_cpu_pct") or 0.0)
    chrome_gpu_cpu = float(process_summary.get("chrome_gpu_cpu_pct") or 0.0)
    window_cpu = float(process_summary.get("window_server_cpu_pct") or 0.0)
    runtime_cpu = float(process_summary.get("current_runtime_cpu_pct") or 0.0)
    automation_cpu = float(process_summary.get("automation_cpu_pct") or 0.0)
    automation_count = int(process_summary.get("automation_count") or 0)
    swap_used_gb = float(swap.get("used_gb") or 0.0)
    swap_used_pct = float(swap.get("used_pct") or 0.0)
    memory_used_pct = float(memory.get("used_pct") or 0.0)
    total_requests_15 = int(request_15m.get("total_requests") or 0)
    polling_rate_15 = float(request_15m.get("polling_rate_pct") or 0.0)

    browser_score = 0
    if chrome_cpu >= 120:
        browser_score += 2
    elif chrome_cpu >= 80:
        browser_score += 1
    if chrome_gpu_cpu >= 70:
        browser_score += 1
    if window_cpu >= 40:
        browser_score += 1

    service_score = 0
    if runtime_cpu >= 90:
        service_score += 2
    elif runtime_cpu >= 70:
        service_score += 1
    if total_requests_15 >= 900 or float(request_15m.get("requests_per_minute") or 0.0) >= 60:
        service_score += 1
    if polling_rate_15 >= 55:
        service_score += 1

    residue_score = 0
    if automation_cpu >= 30:
        residue_score += 2
    elif automation_cpu >= 15:
        residue_score += 1
    if automation_count >= 3:
        residue_score += 1

    memory_score = 0
    if swap_used_gb >= 8 or swap_used_pct >= 85:
        memory_score += 2
    elif swap_used_gb >= 6 or swap_used_pct >= 65:
        memory_score += 1
    if memory_used_pct >= 85:
        memory_score += 1

    issue_defs = [
        (
            "browser_gpu_pressure",
            browser_score,
            "浏览器/GPU 压力",
            "Chrome 渲染与 GPU 进程正在显著吃掉 CPU，WindowServer 跟随放大体感卡顿。",
            "先关闭不用的 dashboard 标签页和高频预览页，优先释放 Chrome GPU / Renderer 压力。",
        ),
        (
            "service_polling_pressure",
            service_score,
            "stable 服务轮询压力",
            "stable 服务正在被多项目轮询持续顶高，/api/conversation-memos /api/codex/runs /api/sessions 等轮询链路是主热区。",
            "先暂停非当前项目的轮询面板，再评估是否需要受控重载 stable 服务。",
        ),
        (
            "automation_residue_pressure",
            residue_score,
            "自动化残留压力",
            "Playwright / chrome-devtools-mcp / 自动化浏览器残留仍在持续占用资源。",
            "先清理长时间闲置的自动化浏览器和残留实例，避免它们继续拖高 Chrome 与系统负载。",
        ),
        (
            "memory_swap_pressure",
            memory_score,
            "内存/Swap 压力",
            "swap 已经偏高，前端和服务端的负载会被放大成更明显的整机卡顿。",
            "完成页面与残留清理后，如 swap 仍持续高位，再安排受控重载或系统重启。",
        ),
    ]

    active_issues = [item for item in issue_defs if item[1] > 0]
    active_issues.sort(key=lambda item: item[1], reverse=True)
    primary = active_issues[0] if active_issues else None

    if primary is None:
        severity = "good"
        headline = "当前压力整体可控"
        summary = "机器层、stable 服务和请求轮询都处于可观察范围，没有形成明显堆积主因。"
        recommended = "维持观察即可，保留当前看板作为巡检入口。"
        primary_type = "normal"
    else:
        primary_type = primary[0]
        severity = "danger" if primary[1] >= 3 else "warn"
        headline = primary[2]
        secondary = active_issues[1][2] if len(active_issues) > 1 else ""
        summary = primary[3]
        if secondary:
            summary = f"{summary} 当前次级放大因子是“{secondary}”。"
        recommended = primary[4]

    return {
        "primary_type": primary_type,
        "severity": severity,
        "headline": headline,
        "summary": summary,
        "recommended_first_action": recommended,
        "active_types": [item[0] for item in active_issues],
        "active_labels": [item[2] for item in active_issues],
    }


def _build_runtime_perf_snapshot_uncached(
    *,
    repo_root: Path,
    environment_name: str,
    port: int,
    project_id: str,
    http_log_path: Path | None = None,
    current_pid: int | None = None,
    now: datetime | None = None,
    max_http_log_bytes: int = 6_000_000,
) -> dict[str, Any]:
    now_local = now or _now_local()
    pid = current_pid if current_pid is not None else os.getpid()
    swap_text = _run_text("sysctl", "vm.swapusage")
    memsize_text = _run_text("sysctl", "-n", "hw.memsize")
    vm_stat_text = _run_text("vm_stat")
    ps_text = _run_text("ps", "-wwaxo", "pid=,pcpu=,pmem=,rss=,etime=,args=")

    try:
        total_memory_bytes = int((memsize_text or "0").strip() or "0")
    except Exception:
        total_memory_bytes = 0

    swap = _parse_swapusage(swap_text)
    memory = _parse_vm_stat(vm_stat_text, total_bytes=total_memory_bytes)
    process_rows = _parse_process_rows(ps_text, current_pid=pid, current_port=port)
    top_processes, automation_processes, process_summary = _build_process_tables(process_rows, current_pid=pid)

    request_rows = _parse_http_log_rows(http_log_path, now=now_local, max_bytes=max_http_log_bytes)
    window_5m = _window_summary(request_rows, now=now_local, minutes=5)
    window_15m = _window_summary(request_rows, now=now_local, minutes=15)
    window_60m = _window_summary(request_rows, now=now_local, minutes=60)

    diagnosis = _build_diagnosis(
        request_15m=window_15m,
        process_summary=process_summary,
        swap=swap,
        memory=memory,
    )
    severity_tone = _as_str(diagnosis.get("severity")).strip() or "good"
    secondary_labels = [
        _as_str(label).strip()
        for label in list(diagnosis.get("active_labels") or [])[1:]
        if _as_str(label).strip()
    ]

    summary_cards = [
        {
            "label": "当前诊断",
            "value": _as_str(diagnosis.get("headline")).strip() or "正常",
            "note": _as_str(diagnosis.get("recommended_first_action")).strip(),
            "tone": severity_tone,
        },
        {
            "label": "Chrome 聚合 CPU",
            "value": _fmt_cpu(process_summary.get("chrome_cpu_pct")),
            "note": f"GPU {_fmt_cpu(process_summary.get('chrome_gpu_cpu_pct'))} · WindowServer {_fmt_cpu(process_summary.get('window_server_cpu_pct'))}",
            "tone": _tone(float(process_summary.get("chrome_cpu_pct") or 0.0), warn=80, danger=120),
        },
        {
            "label": "stable 服务 CPU",
            "value": _fmt_cpu(process_summary.get("current_runtime_cpu_pct")),
            "note": f"PID {int(process_summary.get('current_runtime_pid') or 0)} · {process_summary.get('current_runtime_elapsed') or '-'}",
            "tone": _tone(float(process_summary.get("current_runtime_cpu_pct") or 0.0), warn=70, danger=90),
        },
        {
            "label": "Swap 已用",
            "value": _fmt_gb(swap.get("used_gb")),
            "note": f"{_fmt_pct(swap.get('used_pct'))} / {_fmt_gb(swap.get('total_gb'))}",
            "tone": _tone(float(swap.get("used_pct") or 0.0), warn=65, danger=85),
        },
        {
            "label": "15 分钟请求量",
            "value": _fmt_number(window_15m.get("total_requests")),
            "note": f"{window_15m.get('requests_per_minute') or 0} req/min · 轮询占比 {_fmt_pct(window_15m.get('polling_rate_pct'))}",
            "tone": _tone(float(window_15m.get("requests_per_minute") or 0.0), warn=35, danger=60),
        },
        {
            "label": "自动化残留",
            "value": _fmt_number(len(automation_processes)),
            "note": f"CPU {_fmt_cpu(process_summary.get('automation_cpu_pct'))}",
            "tone": _tone(float(process_summary.get("automation_cpu_pct") or 0.0), warn=15, danger=30),
        },
    ]

    panels = [
        {
            "title": "当前判定",
            "tone": severity_tone,
            "summary": _as_str(diagnosis.get("summary")).strip(),
            "metrics": [
                _metric("主类型", _as_str(diagnosis.get("headline")).strip() or "正常"),
                _metric("严重度", "高压" if severity_tone == "danger" else ("预警" if severity_tone == "warn" else "正常")),
                _metric("建议第一动作", _as_str(diagnosis.get("recommended_first_action")).strip()),
                _metric("次级因素", " / ".join(secondary_labels) or "无"),
            ],
        },
        {
            "title": "机器层",
            "tone": _tone(max(float(process_summary.get("chrome_cpu_pct") or 0.0), float(swap.get("used_pct") or 0.0)), warn=80, danger=120),
            "summary": "把 Chrome、WindowServer、物理内存和 swap 放在一起看，判断是不是浏览器侧先过热。",
            "metrics": [
                _metric("Chrome 聚合 CPU", _fmt_cpu(process_summary.get("chrome_cpu_pct")), f"GPU {_fmt_cpu(process_summary.get('chrome_gpu_cpu_pct'))}"),
                _metric("WindowServer CPU", _fmt_cpu(process_summary.get("window_server_cpu_pct")), "渲染放大因子"),
                _metric("物理内存估算", _fmt_pct(memory.get("used_pct")), f"{_fmt_gb((memory.get('used_bytes') or 0) / float(1024**3))} / {_fmt_gb(total_memory_bytes / float(1024**3) if total_memory_bytes else 0.0)}"),
                _metric("Swap 已用", _fmt_gb(swap.get("used_gb")), f"{_fmt_pct(swap.get('used_pct'))}"),
            ],
        },
        {
            "title": "服务层",
            "tone": _tone(float(process_summary.get("current_runtime_cpu_pct") or 0.0), warn=70, danger=90),
            "summary": "当前看的是正在承接请求的 runtime 进程，不再只看 __health 是否存活。",
            "metrics": [
                _metric("当前 runtime", f"{environment_name} · {port}", f"PID {int(process_summary.get('current_runtime_pid') or 0)}"),
                _metric("服务 CPU", _fmt_cpu(process_summary.get("current_runtime_cpu_pct")), process_summary.get("current_runtime_elapsed") or "-"),
                _metric("服务 RSS", _fmt_mb(process_summary.get("current_runtime_rss_mb")), "常驻内存"),
                _metric("归属项目", _as_str(project_id).strip() or "-"),
            ],
        },
        {
            "title": "请求层",
            "tone": _tone(float(window_15m.get("requests_per_minute") or 0.0), warn=35, danger=60),
            "summary": "聚焦最近 5/15/60 分钟请求量和轮询占比，判断是不是多项目面板叠加把 stable 顶高。",
            "metrics": [
                _metric("5 分钟请求", _fmt_number(window_5m.get("total_requests")), f"{window_5m.get('requests_per_minute') or 0} req/min"),
                _metric("15 分钟请求", _fmt_number(window_15m.get("total_requests")), f"轮询 {_fmt_pct(window_15m.get('polling_rate_pct'))}"),
                _metric("60 分钟请求", _fmt_number(window_60m.get("total_requests")), f"{window_60m.get('requests_per_minute') or 0} req/min"),
                _metric("最近错误率", _fmt_pct(window_15m.get("error_rate_pct")), f"{_fmt_number(window_15m.get('error_count'))} 条 >=400"),
            ],
        },
        {
            "title": "残留层",
            "tone": _tone(float(process_summary.get("automation_cpu_pct") or 0.0), warn=15, danger=30),
            "summary": "看自动化浏览器、调试代理和孤儿进程是否在持续偷资源。",
            "metrics": [
                _metric("残留实例数", _fmt_number(len(automation_processes)), "Playwright / chrome-devtools-mcp / automation Chrome"),
                _metric("残留 CPU", _fmt_cpu(process_summary.get("automation_cpu_pct")), "需要与主浏览器区分"),
                _metric("Top 进程数", _fmt_number(len(top_processes)), "按 CPU 排序取前 10"),
                _metric("静态真源", str(http_log_path.resolve()) if http_log_path else "-", "HTTP 轮询日志"),
            ],
        },
    ]

    windows = [
        {
            "label": f"{window.get('minutes')} 分钟",
            "value": _fmt_number(window.get("total_requests")),
            "count": int(window.get("total_requests") or 0),
            "note": f"{window.get('requests_per_minute') or 0} req/min · 轮询 {_fmt_pct(window.get('polling_rate_pct'))} · 错误 {_fmt_pct(window.get('error_rate_pct'))}",
        }
        for window in (window_5m, window_15m, window_60m)
    ]

    recommendations: list[dict[str, str]] = []
    if diagnosis.get("active_types"):
        for index, label in enumerate(diagnosis.get("active_labels") or [], start=1):
            detail = ""
            if label == "浏览器/GPU 压力":
                detail = "先关不用的项目页、预览页和高频刷新标签页，优先降 Chrome GPU / Renderer。"
            elif label == "stable 服务轮询压力":
                detail = "优先暂停非当前项目的 /api/conversation-memos /api/codex/runs /api/sessions 轮询来源。"
            elif label == "自动化残留压力":
                detail = "清理长时间闲置的 Playwright / chrome-devtools-mcp / automation Chrome。"
            elif label == "内存/Swap 压力":
                detail = "如清理页面后 swap 仍维持高位，再评估受控重载或系统重启。"
            recommendations.append(
                {
                    "priority": f"P{min(index - 1, 2)}",
                    "title": label,
                    "detail": detail or _as_str(diagnosis.get("recommended_first_action")).strip(),
                }
            )
    if not recommendations:
        recommendations.append(
            {
                "priority": "P2",
                "title": "维持观察",
                "detail": "当前未形成明显堆积主因，保留看板用于日常巡检即可。",
            }
        )

    snapshot = {
        "ok": True,
        "generated_at": now_local.isoformat(timespec="seconds"),
        "environment": environment_name,
        "port": int(port),
        "project_id": _as_str(project_id).strip() or "task_dashboard",
        "sessions_snapshot_diagnostics": session_directory_snapshot_diagnostics(
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=repo_root,
        ),
        "diagnosis": diagnosis,
        "summary_cards": summary_cards,
        "panels": panels,
        "windows": windows,
        "top_endpoints": window_15m.get("top_endpoints") or [],
        "top_projects": window_15m.get("top_projects") or [],
        "top_sessions": window_15m.get("top_sessions") or [],
        "top_processes": top_processes,
        "automation_processes": automation_processes,
        "recommendations": recommendations,
        "references": [
            {
                "label": "HTTP 日志",
                "path": str(http_log_path.resolve()) if http_log_path else "-",
                "note": "最近 60 分钟请求来自这里的 tail 聚合。",
            },
            {
                "label": "运行时健康",
                "path": "/__health",
                "note": "确认服务活着，但不替代压力诊断。",
            },
            {
                "label": "进程快照",
                "path": "ps -wwaxo pid=,pcpu=,pmem=,rss=,etime=,args=",
                "note": "用于识别 Chrome / WindowServer / stable / 自动化残留。",
            },
        ],
    }

    return snapshot


def build_runtime_perf_snapshot(
    *,
    repo_root: Path,
    environment_name: str,
    port: int,
    project_id: str,
    http_log_path: Path | None = None,
    current_pid: int | None = None,
    now: datetime | None = None,
    cache_ttl_s: float = 10.0,
    stale_ttl_s: float = 60.0,
    max_http_log_bytes: int = 6_000_000,
) -> dict[str, Any]:
    now_local = now or _now_local()
    pid = current_pid if current_pid is not None else os.getpid()
    cache_key = _perf_snapshot_cache_key(
        environment_name=environment_name,
        port=port,
        project_id=project_id,
        pid=pid,
    )
    cached: tuple[float, dict[str, Any]] | None = None
    now_ts = time.time()
    if cache_ttl_s > 0 or stale_ttl_s > 0:
        with _CACHE_LOCK:
            cached = _SNAPSHOT_CACHE.get(cache_key)
    if cached:
        cached_at, cached_snapshot = cached
        age_s = max(0.0, now_ts - float(cached_at))
        if cache_ttl_s > 0 and age_s < cache_ttl_s:
            return dict(cached_snapshot)
        if stale_ttl_s > 0 and age_s < stale_ttl_s:
            _start_perf_snapshot_refresh(
                cache_key=cache_key,
                repo_root=repo_root,
                environment_name=environment_name,
                port=port,
                project_id=project_id,
                http_log_path=http_log_path,
                current_pid=current_pid,
                max_http_log_bytes=max_http_log_bytes,
            )
            return dict(cached_snapshot)

    snapshot = _build_runtime_perf_snapshot_uncached(
        repo_root=repo_root,
        environment_name=environment_name,
        port=port,
        project_id=project_id,
        http_log_path=http_log_path,
        current_pid=current_pid,
        now=now_local,
        max_http_log_bytes=max_http_log_bytes,
    )
    if cache_ttl_s > 0 or stale_ttl_s > 0:
        _store_perf_snapshot_cache(cache_key, snapshot, cached_at=now_ts)
    return snapshot


def build_performance_diagnostics_page_data(
    script_dir: Path,
    *,
    generated_at: str,
    dashboard: dict[str, Any],
    links: dict[str, Any],
    performance_page_link: str,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "dashboard": dashboard,
        "links": {
            **(links or {}),
            "performance_page": performance_page_link,
        },
        "performance_page": performance_page_link,
        "performance_diagnostics": {
            "title": "生产性能压力诊断看板",
            "subtitle": "把浏览器/GPU、stable 服务、轮询请求和自动化残留放到一页里看，快速判断这次卡顿到底是谁在拖慢。",
            "hero": {
                "kicker": "Ops Pressure Board",
                "headline": "生产性能压力诊断看板",
                "summary": "V1 先解决“为什么越来越卡”的可见性问题：给出压力分类、主因摘要和第一动作，而不是只堆 CPU 数字。",
            },
            "api_path": "/api/runtime/perf-snapshot",
            "refresh_interval_seconds": 15,
            "rebuild_command": f"python3 {script_dir / 'build_project_task_dashboard.py'}",
        },
    }
