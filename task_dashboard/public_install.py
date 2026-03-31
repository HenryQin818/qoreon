from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from task_dashboard.public_agent_activation import (
    activate_public_example_agents,
    write_public_example_startup_batch,
)
from task_dashboard.public_bootstrap import DEFAULT_PROJECT_ID, PUBLIC_EXAMPLE_ROOTS, bootstrap_public_example
from task_dashboard.local_cli_bins import save_local_cli_bin_overrides


def _json_response(url: str, *, timeout_s: float = 5.0) -> dict[str, Any]:
    req = urllib_request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib_request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned invalid payload")
    return payload


def _health_payload(base_url: str, *, timeout_s: float = 5.0) -> dict[str, Any]:
    return _json_response(f"{base_url.rstrip('/')}/__health", timeout_s=timeout_s)


def _wait_for_health(base_url: str, *, timeout_s: float = 30.0, poll_interval_s: float = 0.5) -> dict[str, Any]:
    deadline = time.time() + max(5.0, float(timeout_s))
    last_error = ""
    while time.time() < deadline:
        try:
            payload = _health_payload(base_url, timeout_s=max(2.0, poll_interval_s + 2.0))
        except (urllib_error.URLError, urllib_error.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            time.sleep(max(0.2, float(poll_interval_s)))
            continue
        if bool(payload.get("ok")):
            return payload
        last_error = str(payload.get("error") or payload)
        time.sleep(max(0.2, float(poll_interval_s)))
    raise RuntimeError(f"server health check failed for {base_url}: {last_error or 'timeout'}")


def _normalize_bootstrap_projects(projects: list[str] | tuple[str, ...] | None) -> list[str]:
    values = [str(item or "").strip() for item in (projects or [])]
    if not values:
        values = [DEFAULT_PROJECT_ID]
    normalized: list[str] = []
    for item in values:
        if not item:
            continue
        if item not in PUBLIC_EXAMPLE_ROOTS:
            supported = ", ".join(sorted(PUBLIC_EXAMPLE_ROOTS))
            raise ValueError(f"unknown bootstrap project {item!r}; supported: {supported}")
        if item not in normalized:
            normalized.append(item)
    if not normalized:
        raise ValueError("bootstrap_projects cannot be empty")
    return normalized


def _detect_codex_readiness() -> dict[str, Any]:
    codex_cli = shutil.which("codex") or ""
    sessions_root = Path.home() / ".codex" / "sessions"
    candidate_root = sessions_root if sessions_root.exists() else sessions_root.parent
    if not candidate_root.exists():
        candidate_root = Path.home()
    return {
        "codex_cli_found": bool(codex_cli),
        "codex_cli_path": codex_cli,
        "codex_sessions_root": str(sessions_root),
        "codex_sessions_writable": bool(_path_writable(candidate_root)),
    }


def _is_auth_like_error(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return False
    patterns = [
        "authrequired",
        "invalid access token",
        "unauthorized",
        "www_authenticate_header",
        "forbidden",
        "401",
        "login",
        "sign in",
        "authorization",
        "authentication",
    ]
    return any(p in raw for p in patterns)


def _activation_deferred_result(*, reason: str, message: str, detail: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "skipped": True,
        "deferred_to_local_ai": True,
        "reason": str(reason or "").strip() or "activation_deferred",
        "message": str(message or "").strip(),
        "detail": str(detail or "").strip(),
    }


def _sync_local_cli_bin_overrides(repo_root: Path, *, environment: dict[str, Any]) -> dict[str, Any]:
    codex_cli_path = str(environment.get("codex_cli_path") or "").strip()
    patch = {
        "codex": codex_cli_path,
        "claude": "",
        "opencode": "",
        "gemini": "",
        "trae_cli": "",
    }
    config_path = save_local_cli_bin_overrides(patch, repo_root)
    effective = {"codex": codex_cli_path} if codex_cli_path else {}
    return {
        "config_path": str(config_path),
        "effective": effective,
    }


def _path_writable(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and os_access(path)
    except Exception:
        return False


def os_access(path: Path) -> bool:
    import os

    return os.access(path, os.W_OK)


def _run_build(repo_root: Path) -> dict[str, Any]:
    cmd = [sys.executable, "build_project_task_dashboard.py"]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    output = proc.stdout or ""
    if proc.returncode != 0:
        raise RuntimeError(f"build failed: {output[-1200:]}")
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "output_tail": output[-1200:],
    }


def _pid_on_port(port: int) -> int | None:
    lsof_path = shutil.which("lsof")
    if lsof_path:
        proc = subprocess.run(
            [lsof_path, "-ti", f"tcp:{int(port)}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
        for line in lines:
            try:
                return int(line)
            except ValueError:
                continue
    if os.name == "nt":
        proc = subprocess.run(
            ["netstat", "-ano"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        needle = f":{int(port)}"
        for raw in (proc.stdout or "").splitlines():
            line = raw.strip()
            if needle not in line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local_addr = parts[1]
            state = parts[3] if len(parts) > 4 else ""
            pid_text = parts[-1]
            if not local_addr.endswith(needle):
                continue
            if state.upper() not in {"LISTENING", "ESTABLISHED"}:
                continue
            try:
                return int(pid_text)
            except ValueError:
                continue
    return None


def _wait_for_server_gone(base_url: str, *, timeout_s: float = 8.0, poll_interval_s: float = 0.3) -> None:
    deadline = time.time() + max(1.0, float(timeout_s))
    while time.time() < deadline:
        try:
            _health_payload(base_url, timeout_s=max(1.0, poll_interval_s + 1.0))
        except Exception:
            return
        time.sleep(max(0.1, float(poll_interval_s)))
    raise RuntimeError(f"existing server at {base_url} did not stop in time")


def _terminate_server_on_port(port: int, *, base_url: str) -> int | None:
    pid = _pid_on_port(port)
    if not pid:
        return None
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return pid
    _wait_for_server_gone(base_url, timeout_s=6.0, poll_interval_s=0.3)
    return pid


def _start_server(
    repo_root: Path,
    *,
    base_url: str,
    bind: str,
    port: int,
    expected_project_id: str = "",
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    try:
        payload = _wait_for_health(base_url, timeout_s=2.0, poll_interval_s=0.3)
    except Exception:
        payload = {}
    if payload.get("ok"):
        current_project_id = str(payload.get("project_id") or "").strip()
        wanted_project_id = str(expected_project_id or "").strip()
        if not wanted_project_id or current_project_id == wanted_project_id:
            return {
                "started": False,
                "reused": True,
                "base_url": base_url,
                "health": payload,
            }
        replaced_pid = _terminate_server_on_port(port, base_url=base_url)
        payload = {}

    run_root = repo_root / ".run"
    run_root.mkdir(parents=True, exist_ok=True)
    log_path = run_root / "public-install-server.log"
    meta_path = run_root / "public-install-server.json"
    log_handle = log_path.open("ab")
    cmd = [
        sys.executable,
        "server.py",
        "--bind",
        bind,
        "--port",
        str(port),
        "--static-root",
        "dist",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=repo_root,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_handle.close()
    try:
        payload = _wait_for_health(base_url, timeout_s=timeout_s, poll_interval_s=0.5)
    except Exception as exc:
        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError(f"server start failed, see {log_path}: {exc}") from exc
    meta = {
        "pid": proc.pid,
        "replaced_pid": replaced_pid if 'replaced_pid' in locals() else None,
        "base_url": base_url,
        "bind": bind,
        "port": int(port),
        "log_path": str(log_path),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "started": True,
        "reused": False,
        "base_url": base_url,
        "pid": proc.pid,
        "log_path": str(log_path),
        "meta_path": str(meta_path),
        "health": payload,
    }


def install_public_bundle(
    repo_root: Path,
    *,
    bootstrap_projects: list[str] | tuple[str, ...] | None = None,
    build_pages: bool = True,
    start_server: bool = False,
    bind: str = "127.0.0.1",
    port: int = 18770,
    base_url: str | None = None,
    activate_project: str = "",
    activation_run_samples: bool = False,
    token: str = "",
    include_optional: bool = False,
    wait_timeout_s: float = 240.0,
    poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    selected_projects = _normalize_bootstrap_projects(bootstrap_projects)
    selected_base_url = str(base_url or f"http://127.0.0.1:{int(port)}").strip()
    codex_ready = _detect_codex_readiness()
    cli_bins = _sync_local_cli_bin_overrides(repo_root, environment=codex_ready)

    bootstrap_results: list[dict[str, Any]] = []
    startup_batches: list[dict[str, Any]] = []
    for project_id in selected_projects:
        result = bootstrap_public_example(repo_root, project_id=project_id)
        bootstrap_results.append(
            {
                "project_id": project_id,
                **result,
            }
        )
        startup_batches.append(
            write_public_example_startup_batch(
                repo_root,
                project_id=project_id,
                include_optional=include_optional,
            )
        )

    build_result: dict[str, Any] | None = None
    if build_pages:
        build_result = _run_build(repo_root)

    server_result: dict[str, Any] | None = None
    if start_server:
        server_result = _start_server(
            repo_root,
            base_url=selected_base_url,
            bind=bind,
            port=port,
            expected_project_id=selected_projects[0] if selected_projects else "",
        )

    activation_result: dict[str, Any] | None = None
    normalized_activate_project = str(activate_project or "").strip()
    if normalized_activate_project:
        if normalized_activate_project not in PUBLIC_EXAMPLE_ROOTS:
            supported = ", ".join(sorted(PUBLIC_EXAMPLE_ROOTS))
            raise ValueError(f"unknown activate_project={normalized_activate_project!r}; supported: {supported}")
        if not codex_ready.get("codex_cli_found"):
            activation_result = {
                "ok": False,
                "skipped": True,
                "reason": "codex_not_found",
                "message": "当前电脑未检测到 codex，可先完成页面安装，后续再补 Agent 激活。",
            }
        elif not codex_ready.get("codex_sessions_writable"):
            activation_result = {
                "ok": False,
                "skipped": True,
                "reason": "codex_sessions_not_writable",
                "message": "当前电脑的 ~/.codex/sessions 不可写，可先完成页面安装，修复后再激活 Agent。",
            }
        else:
            try:
                _wait_for_health(selected_base_url, timeout_s=5.0, poll_interval_s=0.3)
            except Exception:
                activation_result = {
                    "ok": False,
                    "skipped": True,
                    "reason": "server_not_ready_for_activation",
                    "message": "Agent 激活需要本地服务已启动；请重新执行带 --start-server 的安装命令，或先启动 server.py。",
                }
            else:
                try:
                    activation_result = activate_public_example_agents(
                        repo_root,
                        base_url=selected_base_url,
                        project_id=normalized_activate_project,
                        token=token,
                        include_optional=include_optional,
                        run_sample_actions=bool(activation_run_samples),
                        wait_timeout_s=wait_timeout_s,
                        poll_interval_s=poll_interval_s,
                    )
                except RuntimeError as exc:
                    err_text = str(exc or "").strip()
                    if _is_auth_like_error(err_text):
                        activation_result = _activation_deferred_result(
                            reason="codex_noninteractive_auth_blocked",
                            message="检测到 Codex 非交互创建会话被认证/授权阻塞；页面安装已完成，但默认 Agent 会话改为交给本机 AI 接管。",
                            detail=err_text,
                        )
                    else:
                        activation_result = _activation_deferred_result(
                            reason="codex_noninteractive_probe_failed",
                            message="页面安装已完成，但默认 Agent 会话创建未通过首轮探测；请把启动批次交给本机 AI 接管，或确认本机 codex 完成一次非交互 exec 后再重试。",
                            detail=err_text,
                        )

    run_root = repo_root / ".run"
    run_root.mkdir(parents=True, exist_ok=True)
    result_path = run_root / "public-install-result.json"
    startup_batch_hint = ""
    if startup_batches:
        startup_batch_hint = str(startup_batches[0].get("markdown_path") or "").strip()
    manifest = {
        "schema_version": "1.0",
        "public_safe": True,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "repo_root": str(repo_root),
        "bootstrap_projects": selected_projects,
        "build_pages": bool(build_pages),
        "start_server": bool(start_server),
        "activate_project": normalized_activate_project,
        "environment": codex_ready,
        "cli_bins": cli_bins,
        "results": {
            "bootstrap": bootstrap_results,
            "startup_batches": startup_batches,
            "build": build_result,
            "server": server_result,
            "activation": activation_result,
        },
        "next_steps": [
            "打开 docs/public/quick-start.md 了解 standard_project 的安装与启动路径",
            "打开 project-task-dashboard 页面确认 standard_project 可见",
            (
                f"若要让 AI 在用户电脑上继续接手，把 docs/public/ai-bootstrap.md 与 {startup_batch_hint} 发给它"
                if startup_batch_hint
                else "若要让 AI 在用户电脑上继续接手，把 docs/public/ai-bootstrap.md 与启动批次文件发给它"
            ),
        ],
    }
    if not normalized_activate_project:
        manifest["agent_activation_state"] = "skipped_by_flag_or_mode"
        manifest["next_steps"].append(
            "当前安装结果不包含默认 Agent 会话；如果你希望安装后 standard_project 里直接出现 Agent，请执行 python3 scripts/start_standard_project.py"
        )
        manifest["next_steps"].append(
            "若要在创建默认会话后，再补首轮培训/职责复述/示例动作，可执行 python3 scripts/start_standard_project.py --with-agents"
        )
    elif activation_result and activation_result.get("ok"):
        manifest["agent_activation_state"] = "sessions_created"
        manifest["next_steps"].append(
            "标准项目默认通道会话已经创建；如需首轮培训与职责复述，可执行 python3 scripts/start_standard_project.py --with-agents"
        )
    elif activation_result and activation_result.get("deferred_to_local_ai"):
        manifest["agent_activation_state"] = "deferred_to_local_ai"
        manifest["next_steps"].append(
            "页面和 standard_project 已安装完成，但默认 Agent 会话未自动建出；请把 docs/public/ai-bootstrap.md 与 startup-batch.md 交给本机 AI 接手。"
        )
        manifest["next_steps"].append(
            "如果确认本机 codex 已能完成一次非交互 exec，再重试 python3 scripts/start_standard_project.py 或 python3 scripts/start_standard_project.py --with-agents"
        )
    else:
        manifest["agent_activation_state"] = "skipped_or_failed"
    result_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "result_path": str(result_path),
        "bootstrap_projects": selected_projects,
        "build": build_result,
        "server": server_result,
        "activation": activation_result,
        "startup_batches": startup_batches,
        "environment": codex_ready,
        "cli_bins": cli_bins,
        "agent_activation_state": manifest["agent_activation_state"],
    }
