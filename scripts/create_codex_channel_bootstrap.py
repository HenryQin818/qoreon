#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex-only 通道一键创建脚本（V1）

覆盖：
- 新建通道（config.toml + 目录骨架，通过 task-dashboard API）
- 创建 Codex 会话（首条 seed message 防止默认标题污染）
- 写入 `.sessions/<project_id>.json` 单一真源
- Codex App 可见性补录（desktopize session_meta + history 标题索引）
- 初始化消息 + OK 连通性验收（通过 CCB announce + run 轮询）
- 通道/总控收件箱关键摘要留痕
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from task_dashboard.task_identity import generate_task_id, render_task_front_matter

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS = 4
DESKTOPIZE_SESSION_FILE_RETRY_DELAY_S = 2.0
API_SESSION_CHANNEL_READY_MAX_ATTEMPTS = 6
API_SESSION_CHANNEL_READY_RETRY_DELAY_S = 0.75


def _now_local() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime())


def _now_iso_basic() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _die(msg: str, code: int = 1) -> "NoReturn":
    print(f"[ERR] {msg}", file=sys.stderr)
    raise SystemExit(code)


def _info(msg: str) -> None:
    print(f"[INFO] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _is_channel_not_found_error(exc: BaseException) -> bool:
    text = str(exc or "").lower()
    return "channel not found" in text and ("http 404" in text or "404" in text)


def _safe_stem(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("/", "-").replace("\\", "-").replace(":", "-")
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"[<>\"|?*]", "-", s)
    return s[:160] if len(s) > 160 else s


def _normalize_index(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return s
    if s.isdigit():
        return s.zfill(2)
    return s


def _guess_desktop_cwd(repo_root: Path) -> str:
    txt = str(repo_root)
    if "/workspace/" in txt:
        candidate = Path(txt.replace("/workspace/", "/Desktop/", 1))
        if candidate.exists():
            return str(candidate)
    return txt


def _resolve_task_root(repo_root: Path, task_root_rel: str) -> Path:
    raw = Path(str(task_root_rel or "").strip())
    if raw.is_absolute():
        return raw.resolve()
    candidates: list[Path] = []
    candidates.append((repo_root / raw).resolve())
    cwd = Path.cwd().resolve()
    candidates.append((cwd / raw).resolve())
    # 兼容 config 使用“工作区根相对路径”，而脚本位于仓库子目录时的重复拼接问题。
    for base in [repo_root, cwd]:
        for parent in list(base.parents)[:8]:
            candidates.append((parent / raw).resolve())
    seen: set[str] = set()
    for c in candidates:
        k = str(c)
        if k in seen:
            continue
        seen.add(k)
        if c.exists():
            return c
    # 没找到时返回首选路径，保留可读错误信息
    return candidates[0]


def _load_projects_config(config_path: Path) -> dict[str, Any]:
    if tomllib is None:
        return {"__parse_error__": "tomllib unavailable"}
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"__parse_error__": str(e)}
    if not isinstance(data, dict):
        return {"__parse_error__": "invalid parsed object"}
    return data


def _find_project_cfg(config_obj: dict[str, Any], project_id: str) -> dict[str, Any]:
    for p in config_obj.get("projects") or []:
        if not isinstance(p, dict):
            continue
        if str(p.get("id") or "").strip() == project_id:
            return p
    return {}


def _extract_project_task_root_rel_regex(config_text: str, project_id: str) -> str:
    content = str(config_text or "")
    pid = re.escape(str(project_id or "").strip())
    if not pid:
        return ""
    blocks = list(re.finditer(r"(?m)^\[\[projects\]\]\s*$", content))
    for i, m in enumerate(blocks):
        start = m.start()
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(content)
        block = content[start:end]
        if not re.search(rf"(?m)^\s*id\s*=\s*['\"]{pid}['\"]\s*$", block):
            continue
        tm = re.search(r"(?m)^\s*task_root_rel\s*=\s*['\"]([^'\"]+)['\"]\s*$", block)
        if tm:
            return str(tm.group(1) or "").strip()
    return ""


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _resolve_runtime_sessions_project_path(health_data: Any, project_id: str) -> Optional[Path]:
    if not isinstance(health_data, dict):
        return None
    pid = str(project_id or "").strip()
    if not pid:
        return None
    raw_sessions_file = str(health_data.get("sessionsFile") or "").strip()
    if raw_sessions_file:
        try:
            sessions_file = Path(raw_sessions_file).expanduser().resolve()
            return sessions_file.parent / f"{pid}.json"
        except Exception:
            pass
    raw_runs_dir = str(health_data.get("runsDir") or "").strip()
    if raw_runs_dir:
        try:
            runs_dir = Path(raw_runs_dir).expanduser().resolve()
            return runs_dir.parent / ".sessions" / f"{pid}.json"
        except Exception:
            pass
    return None


def _desktopize_session_file_missing(stdout: str, stderr: str) -> bool:
    combined = "\n".join(part for part in [stdout, stderr] if part).lower()
    return "session file not found" in combined


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        prev = path.read_text(encoding="utf-8")
    else:
        prev = ""
    sep = "" if (not prev or prev.endswith("\n")) else "\n"
    _write_text(path, prev + sep + text)


def _http_request_json(
    *,
    method: str,
    url: str,
    payload: Optional[dict[str, Any]] = None,
    token: str = "",
    timeout_s: int = 30,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data: Optional[bytes] = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["X-TaskDashboard-Token"] = token
    req = urlrequest.Request(url=url, data=data, headers=headers, method=method.upper())
    try:
        with urlrequest.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {}
            return json.loads(raw)
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {body}") from e
    except urlerror.URLError as e:
        raise RuntimeError(f"{method} {url} failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"{method} {url} failed: {e}") from e


@dataclass
class BootstrapNames:
    channel_dir_name: str
    session_title: str
    codex_sessions_desc: str
    task_filename: str
    task_heading: str


@dataclass
class BootstrapResult:
    ok: bool
    project_id: str
    channel_name: str
    session_id: str = ""
    session_title: str = ""
    init_run_id: str = ""
    init_run_status: str = ""
    ok_run_id: str = ""
    ok_run_status: str = ""
    ok_last_message: str = ""
    training_run_id: str = ""
    task_file: str = ""
    channel_inbox: str = ""
    master_inbox: str = ""
    sessions_project_path: str = ""
    bootstrap_result_path: str = ""
    desktop_cwd: str = ""
    warnings: list[str] | None = None


class Bootstrapper:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(__file__).resolve().parents[1]
        self.config_path = self.repo_root / "config.toml"
        self.project_id = str(args.project_id).strip()
        self.port = int(args.port)
        self.base_url = str(args.base_url or f"http://127.0.0.1:{self.port}").rstrip("/")
        self.token = str(args.token or os.environ.get("TASK_DASHBOARD_TOKEN") or "").strip()
        self.desktop_cwd = str(args.desktop_cwd or _guess_desktop_cwd(self.repo_root))
        self.names = self._build_names()
        self._warnings: list[str] = []
        self._used_local_session_fallback = False
        self.health_data: dict[str, Any] = {}

        self._config_text = self.config_path.read_text(encoding="utf-8")
        cfg = _load_projects_config(self.config_path)
        parse_error = str(cfg.get("__parse_error__") or "").strip() if isinstance(cfg, dict) else ""
        self.project_cfg = _find_project_cfg(cfg if isinstance(cfg, dict) else {}, self.project_id)
        if parse_error:
            self._warnings.append(f"config.toml 解析异常，已使用兼容读取: {parse_error}")
            _warn(f"config.toml 解析异常，切换兼容读取: {parse_error}")
        task_root_rel = str(self.project_cfg.get("task_root_rel") or "").strip()
        if not self.project_cfg:
            # 当 config 存在重复键导致 tomllib 失败时，退回正则提取任务根路径。
            self.project_cfg = {"id": self.project_id}
        if not task_root_rel:
            task_root_rel = _extract_project_task_root_rel_regex(self._config_text, self.project_id)
        if not task_root_rel:
            _die(f"project {self.project_id} 缺少 task_root_rel")
        self.task_root = _resolve_task_root(self.repo_root, task_root_rel)
        self.channel_root = self.task_root / self.names.channel_dir_name
        self.task_file = self.channel_root / "任务" / self.names.task_filename
        self.channel_inbox = self.channel_root / "沟通-收件箱.md"
        self.master_inbox = self._detect_master_inbox()
        self.sessions_dir = self.repo_root / ".sessions"
        self.sessions_project_path = self.sessions_dir / f"{self.project_id}.json"
        self.runtime_sessions_project_path: Optional[Path] = None
        self.result_path = self.channel_root / "产出物" / "沉淀" / "bootstrap-result.json"

        skill_root = Path("/tmp/qoreon-home/qoreon-skills/codex-sessions-registry/scripts")
        self.desktopize_script = skill_root / "desktopize_taskboard_session.py"

    def _build_names(self) -> BootstrapNames:
        kind = str(self.args.channel_kind).strip()
        idx = _normalize_index(self.args.channel_index)
        cname = str(self.args.channel_name).strip()
        scope = str(self.args.channel_scope or "").strip()
        if not kind or not idx or not cname:
            _die("channel-kind / channel-index / channel-name 不能为空")
        if any(ch in '/\\:*?"<>|' for ch in kind):
            _die("channel-kind 包含非法字符")
        channel_dir_name = f"{kind}{idx}-{cname}"
        if scope:
            channel_dir_name += f"（{scope}）"
        session_title = f"【Qoreon】{channel_dir_name}（主会话）"
        codex_desc = f"{kind}{idx}-{cname}（主会话）"
        task_title = str(self.args.task_title).strip()
        if not task_title:
            _die("--task-title 不能为空")
        task_stem = f"{idx}-1-{cname}-{task_title}"
        task_filename = f"【待开始】【任务】{_safe_stem(task_stem)}.md"
        return BootstrapNames(
            channel_dir_name=channel_dir_name,
            session_title=session_title,
            codex_sessions_desc=codex_desc,
            task_filename=task_filename,
            task_heading=task_stem,
        )

    def _detect_master_inbox(self) -> Optional[Path]:
        preferred = self.task_root / "主体-总控（合并与验收）" / "沟通-收件箱.md"
        if preferred.exists():
            return preferred
        for p in sorted(self.task_root.glob("主体-总控*/沟通-收件箱.md")):
            return p
        return None

    def run(self) -> BootstrapResult:
        _info(f"目标通道: {self.names.channel_dir_name}")
        _info(f"目标会话标题: {self.names.session_title}")
        self._preflight()

        if self.args.dry_run:
            return self._dry_run_result()

        self._ensure_scripts_exist()
        self._create_channel()
        self._write_main_task_file()
        session_id = self._create_session()
        if not self.args.no_desktopize:
            self._desktopize_session(session_id)
        init_run_id, init_run_status = self._send_init_message(session_id)
        ok_run_id = ""
        ok_run_status = ""
        ok_last_message = ""
        training_run_id = ""
        if not self.args.no_ok_check:
            ok_run_id, ok_run_status, ok_last_message = self._send_ok_check(session_id)
        if not self.args.no_training_message:
            training_run_id = self._send_training_message(session_id)
        self._append_inboxes(
            session_id=session_id,
            init_run_id=init_run_id,
            init_run_status=init_run_status,
            ok_run_id=ok_run_id,
            ok_run_status=ok_run_status,
            ok_last_message=ok_last_message,
            training_run_id=training_run_id,
        )
        result = BootstrapResult(
            ok=True,
            project_id=self.project_id,
            channel_name=self.names.channel_dir_name,
            session_id=session_id,
            session_title=self.names.session_title,
            init_run_id=init_run_id,
            init_run_status=init_run_status,
            ok_run_id=ok_run_id,
            ok_run_status=ok_run_status,
            ok_last_message=ok_last_message,
            training_run_id=training_run_id,
            task_file=str(self.task_file),
            channel_inbox=str(self.channel_inbox),
            master_inbox=str(self.master_inbox) if self.master_inbox else "",
            sessions_project_path=str(self.sessions_project_path),
            bootstrap_result_path=str(self.result_path),
            desktop_cwd=self.desktop_cwd,
            warnings=list(self._warnings),
        )
        self._write_result_json(result)
        return result

    def _preflight(self) -> None:
        if not self.config_path.exists():
            _die(f"config.toml 不存在: {self.config_path}")
        if not self.task_root.exists():
            _die(f"task root 不存在: {self.task_root}")
        if not Path(self.desktop_cwd).exists():
            _die(f"desktop-cwd 不存在: {self.desktop_cwd}")
        if self.channel_root.exists():
            _die(f"目标通道目录已存在: {self.channel_root}")
        if self.task_file.exists():
            _die(f"主任务文件已存在: {self.task_file}")
        config_text = self.config_path.read_text(encoding="utf-8")
        if self.names.channel_dir_name in config_text:
            _die(f"config.toml 中已存在同名通道: {self.names.channel_dir_name}")
        self._health_check()
        if self.args.no_desktopize:
            self._warnings.append("已跳过 desktopize，可见性补录未执行")
        if self.args.no_ok_check:
            self._warnings.append("已跳过 OK 连通性验收")
        if self.args.no_training_message:
            self._warnings.append("已跳过 Agent 启动培训消息")

    def _health_check(self) -> None:
        if self.args.skip_health_check:
            _warn("跳过 /__health 检查（--skip-health-check）")
            return
        url = f"{self.base_url}/__health"
        _info(f"健康检查: {url}")
        try:
            data = _http_request_json(method="GET", url=url, token="", timeout_s=10)
        except Exception as e:
            _die(f"健康检查失败: {e}")
        if not isinstance(data, dict):
            _die("健康检查返回非 JSON 对象")
        self.health_data = dict(data)
        self.runtime_sessions_project_path = _resolve_runtime_sessions_project_path(data, self.project_id)
        _info(f"健康检查通过: keys={','.join(sorted(list(data.keys()))[:8])}")

    def _iter_project_session_store_paths(self) -> list[Path]:
        paths: list[Path] = [self.sessions_project_path]
        runtime_path = self.runtime_sessions_project_path
        if isinstance(runtime_path, Path):
            paths.append(runtime_path)
        out: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            try:
                key = str(path.resolve())
            except Exception:
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
        return out

    def _ensure_scripts_exist(self) -> None:
        if self.args.no_desktopize:
            return
        if not self.desktopize_script.exists():
            _die(f"desktopize_taskboard_session.py 不存在: {self.desktopize_script}")

    def _dry_run_result(self) -> BootstrapResult:
        plan = {
            "mode": "dry-run",
            "base_url": self.base_url,
            "project_id": self.project_id,
            "channel_name": self.names.channel_dir_name,
            "session_title": self.names.session_title,
            "task_file": str(self.task_file),
            "desktop_cwd": self.desktop_cwd,
            "steps": [
                "POST /api/channels",
                "write main task file",
                "POST /api/sessions (with first_message)",
                "desktopize_taskboard_session.py",
                "POST /api/codex/announce (init)",
                "POST /api/codex/announce (OK check)",
                "POST /api/codex/announce (startup training)",
                "append inbox summaries",
                "write bootstrap-result.json",
            ],
        }
        print(_json_dumps(plan))
        return BootstrapResult(
            ok=True,
            project_id=self.project_id,
            channel_name=self.names.channel_dir_name,
            session_title=self.names.session_title,
            task_file=str(self.task_file),
            channel_inbox=str(self.channel_inbox),
            master_inbox=str(self.master_inbox) if self.master_inbox else "",
            sessions_project_path=str(self.sessions_project_path),
            bootstrap_result_path=str(self.result_path),
            desktop_cwd=self.desktop_cwd,
            warnings=list(self._warnings),
        )

    def _create_channel(self) -> None:
        _info("创建通道（/api/channels）")
        payload = {
            "projectId": self.project_id,
            "name": self.names.channel_dir_name,
            "desc": str(self.args.desc or self.names.channel_dir_name),
        }
        resp = _http_request_json(
            method="POST",
            url=f"{self.base_url}/api/channels",
            payload=payload,
            token=self.token,
            timeout_s=30,
        )
        if not isinstance(resp, dict) or not resp.get("ok"):
            _die(f"创建通道失败: {_json_dumps(resp)}")
        if not self.channel_root.exists():
            _die(f"通道 API 返回成功但目录未出现: {self.channel_root}")

    def _write_main_task_file(self) -> None:
        _info("生成主任务文件")
        goal = str(self.args.goal or "").strip() or "建立通道后，开展该场景的结构化治理与执行推进。"
        desc = str(self.args.desc or "").strip() or self.names.channel_dir_name
        content = self._render_task_markdown(goal=goal, desc=desc)
        _write_text(self.task_file, content)

    def _render_task_markdown(self, *, goal: str, desc: str) -> str:
        scope_line = str(self.args.channel_scope or "").strip()
        kind = str(self.args.channel_kind).strip()
        idx = _normalize_index(self.args.channel_index)
        title = self.names.task_heading
        front_matter = render_task_front_matter(task_id=generate_task_id())
        return front_matter + f"""# {title}
更新时间：{_now_local()}

## 目标
- {goal}
- 建立 `{self.names.channel_dir_name}` 的主任务与会话基础结构，确保后续执行、回执、验收留痕可持续。

## 背景
- 通道说明：{desc}
- 通道类型：`{kind}`
- 通道编号：`{idx}`
- 通道范围：{scope_line or '未单独填写（以通道名为准）'}

## 范围（V1）
### 覆盖
- 全局任务/通道/agent 资源关系的结构化梳理（按本通道后续任务拆分推进）
- 本通道主会话协作与回执留痕
- 与总控通道的关键节点同步（收件箱摘要）

### 暂不覆盖
- 非本通道直接负责的研发实现（需按任务再派发）
- 其他通道既有历史数据批量清洗（需独立任务）

## 交付物
1. 本通道结构化治理方案与任务拆分
2. 关键执行回执与验收反馈
3. 可复用的关系视图/规则沉淀（放在 `产出物/沉淀/`）

## 执行约束
- 目录即分工、文件名即状态
- 契约兼容优先：新增字段可接受，禁止破坏性改名
- 关键结论同步写入通道收件箱，必要时抄录总控收件箱

## 下一步
1. 由主会话确认启动计划（目标、边界、优先级）
2. 按需要派发子任务并回收结果
3. 收敛为可视化/结构化视图与沉淀文档
"""

    def _target_cli_type(self) -> str:
        return str(getattr(self.args, "target_cli_type", "") or "").strip().lower()

    def _is_gemini_target(self) -> bool:
        return self._target_cli_type() == "gemini"

    def _build_seed_communication_rule(self) -> str:
        if self._is_gemini_target():
            return (
                "通信与工具规则：目标为 `cli_type=gemini` 时，只使用当前实际可见工具，"
                "例如 `read_file`、`grep_search`、`cli_help`；不要调用不存在的 `run_shell_command`、"
                "`list_directory` 或 Codex/Claude 专属工具。初始化阶段不强制发送通讯录验证消息；"
                "能读取项目真源则输出初始化结构，不能读取则回唯一阻塞。正式消息仍以 "
                "`announce_run_id + target_session_id一致 + visible_in_channel_chat=true` 为送达证据，"
                "message CLI 默认优先读取 live stable 真源 `.runtime/stable/.sessions`，不得伪造已送达。"
            )
        return (
            "通信规则：正式跨 Agent 消息优先用 "
            "`python3 -m task_dashboard.message_cli send|receipt --to-agent <目标Agent> --wait-verify --json`；"
            "CLI 只是 `POST /api/codex/announce` 封装，`--wait-verify` 只等送达证据，"
            "默认优先读取 live stable 真源 `.runtime/stable/.sessions`；目标阻塞时按 "
            "`blocking_error.lookup_roots` 与 `blocking_error.next_action` 转会话治理，不要翻源码、旧 registry 或 `.sessions` 旁路发送。"
        )

    def _build_training_communication_rules(self) -> str:
        if self._is_gemini_target():
            return (
                "6. Gemini 工具降级口径：你是 `cli_type=gemini` Agent，只能使用当前实际可见工具，"
                "例如 `read_file`、`grep_search`、`cli_help`；不要调用不存在的 `run_shell_command`、"
                "`list_directory` 或 Codex/Claude 专属工具。\n"
                "7. 初始化阶段不强制发送“通讯录验证消息”；能读取项目真源则按固定结构回复，"
                "不能读取则回唯一阻塞和所需协同，不伪造已完成。\n"
                "8. 后续如需正式发消息，可优先尝试 `python3 -m task_dashboard.message_cli send|receipt --to-agent <目标Agent> --wait-verify --json`；"
                "`send/receipt` 都只是 `POST /api/codex/announce` 的封装，不是第二套消息协议。\n"
                "9. `--wait-verify` 只等待送达证据，不等待目标 Agent 完成业务处理；"
                "送达证据必须是 `announce_run_id + target_session_id一致 + visible_in_channel_chat=true`。\n"
                "10. CLI 默认优先读取 live stable 真源 `.runtime/stable/.sessions`，再兼容回退根 `.sessions`；跨项目发送不要手工补复杂 root。\n"
                "11. 目标缺失、多候选、会话不可用或上下文耗尽时，按 CLI 输出的 "
                "`blocking_error.lookup_roots` 与 `blocking_error.next_action` 转会话治理/主负责位处理；不要手工翻 `message_cli.py`、旧 registry 或 `.sessions` 旁路发送。\n"
                "12. 若声称“已发出正式消息/已通知通道/已送达”，至少要带 `announce_run_id`；没有就只能写“已生成待发送正文”或“阻塞未发送”。\n"
                "13. 回执至少包含：当前结论 / 是否通过或放行 / 唯一阻塞 / 关键路径或 run_id / 下一步动作。\n"
                "14. 不允许只改文件不回消息，除非明确是 `notify_only`。\n"
            )
        return (
            "6. 正式发消息的最短路径优先用："
            "`python3 -m task_dashboard.message_cli send --to-agent <目标Agent> --mode dialog_now --wait-verify --json`；"
            "需要业务回执时改用 `--mode task_with_receipt --callback-session-id <回执会话>`。\n"
            "7. 回送结构化结果优先用 `python3 -m task_dashboard.message_cli receipt --to-agent <目标Agent> --wait-verify --json`；"
            "`send/receipt` 都只是 `POST /api/codex/announce` 的封装，不是第二套消息协议。\n"
            "8. `--wait-verify` 只等待送达证据，不等待目标 Agent 完成业务处理；"
            "送达证据必须是 `announce_run_id + target_session_id一致 + visible_in_channel_chat=true`。\n"
            "9. CLI 默认优先读取 live stable 真源 `.runtime/stable/.sessions`，再兼容回退根 `.sessions`；跨项目发送不要手工补复杂 root。\n"
            "10. 目标缺失、多候选、会话不可用或上下文耗尽时，按 CLI 输出的 "
            "`blocking_error.lookup_roots` 与 `blocking_error.next_action` 转会话治理/主负责位处理；不要手工翻 `message_cli.py`、旧 registry 或 `.sessions` 旁路发送。\n"
            "11. 若声称“已发出正式消息/已通知通道/已送达”，至少要带 `announce_run_id`；没有就只能写“已生成待发送正文”或“阻塞未发送”。\n"
            "12. 回执至少包含：当前结论 / 是否通过或放行 / 唯一阻塞 / 关键路径或 run_id / 下一步动作。\n"
            "13. 不允许只改文件不回消息，除非明确是 `notify_only`。\n"
        )

    def _build_seed_message(self) -> str:
        goal = str(self.args.goal or "").strip() or "建立本通道的结构化治理起点并输出启动计划。"
        return (
            f"你是通道【{self.names.channel_dir_name}】的主会话。\n"
            f"本次创建用途：{goal}\n"
            "请按本项目‘目录即分工/文件名即状态’规则工作，优先输出简洁启动计划与首批信息收集清单。\n"
            f"{self._build_seed_communication_rule()}"
        )

    def _build_init_announce_message(self) -> str:
        goal = str(self.args.goal or "").strip() or "建立本通道的结构化治理起点并输出启动计划。"
        return (
            f"[通道初始化]\n"
            f"通道：{self.names.channel_dir_name}\n"
            f"主任务：{self.names.task_heading}\n"
            f"当前目标：{goal}\n"
            "请仅回复：已受理 + 启动计划（3-5条）。"
        )

    def _build_training_message(self, session_id: str) -> str:
        return (
            "[Agent启动培训]\n"
            f"你是通道【{self.names.channel_dir_name}】的新 Agent。\n"
            f"你的 session_id：{session_id}\n\n"
            "你先完成 5 件事：\n"
            "1. 了解项目现状：先以当前项目主线、当前阶段与通道职责为准，不自行扩题。\n"
            "2. 学习所在通道当前文件夹知识：优先阅读 README.md、任务、问题、反馈（如存在）、产出物/材料/沉淀，总结当前方法、规则、经验与未收口事项。\n"
            "3. 若通道内已有任务、问题簇或冻结主线，先判断“并入现有主线”还是“新开独立线”，不要直接另起炉灶。\n"
            "4. 启动顺序固定为：先完成知识阅读并回复“已完成初始化”，再开始首个动作。\n"
            "5. 按项目协作规范参与团队沟通：除非消息明确写“无需回执/仅接收”，否则处理完消息后默认回给原发送 Agent。\n\n"
            "协作硬要求：\n"
            f"1. 你后续给任何 Agent 发消息时，必须带上自己的 session_id（{session_id}）。\n"
            f"2. 推荐固定写法：`[当前发信Agent: <你的Agent名称>; session_id={session_id}; alias=<你的alias>]`\n"
            "3. 若消息中有 `callback_to.session_id`，优先回给该 session；否则回原发送 Agent 的 session。\n"
            "4. 跨 Agent / 跨通道正式协作必须走系统正式发送链路；内部 spawn 或草稿整理不算“已通知”。\n"
            "5. `task_with_receipt / dialog_now` 收到后要先首回执，处理完成后再回结构化结果；只有明确是 `notify_only` 才可不回。\n"
            f"{self._build_training_communication_rules()}\n"
            "请仅回复：已完成初始化 + 当前主线 + 唯一阻塞（无则写无） + 首个动作。"
        )

    def _create_session(self) -> str:
        _info("创建 Codex 会话（/api/sessions，带 first_message）")
        payload = {
            "project_id": self.project_id,
            "channel_name": self.names.channel_dir_name,
            "cli_type": "codex",
            "alias": str(self.args.session_alias or "").strip(),
            "agent_name": str(self.args.session_alias or getattr(self.names, "session_title", "") or self.names.channel_dir_name or "").strip(),
            "first_message": self._build_seed_message(),
        }
        api_timeout_s = max(5, int(self.args.api_session_timeout_s))
        max_attempts = max(1, int(API_SESSION_CHANNEL_READY_MAX_ATTEMPTS))
        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = _http_request_json(
                        method="POST",
                        url=f"{self.base_url}/api/sessions",
                        payload=payload,
                        token=self.token,
                        timeout_s=api_timeout_s,
                    )
                    session = resp.get("session") if isinstance(resp, dict) else None
                    if not isinstance(session, dict):
                        raise RuntimeError(f"无 session 字段: {_json_dumps(resp)}")
                    sid = str(session.get("id") or "").strip()
                    if not sid:
                        raise RuntimeError(f"session.id 为空: {_json_dumps(resp)}")
                    suffix = "" if attempt == 1 else f"（API 第 {attempt} 次尝试）"
                    _info(f"会话创建成功{suffix}: {sid}")
                    return sid
                except Exception as e:
                    if not _is_channel_not_found_error(e) or attempt >= max_attempts:
                        raise
                    delay_s = min(API_SESSION_CHANNEL_READY_RETRY_DELAY_S * attempt, 3.0)
                    _warn(
                        "新通道刚创建后 /api/sessions 暂未识别 channel，"
                        f"{delay_s:.2f}s 后重试 ({attempt}/{max_attempts})"
                    )
                    time.sleep(delay_s)
        except Exception as e:
            _warn(f"/api/sessions 创建失败，切换本地直连 fallback: {e}")
            sid = self._create_session_via_local_codex(
                alias=str(self.args.session_alias or "").strip(),
                seed_message=self._build_seed_message(),
            )
            self._warnings.append("已使用本地直连建会话 fallback（/api/sessions 当前异常）")
            self._used_local_session_fallback = True
            _info(f"会话创建成功（fallback）: {sid}")
            return sid

    def _create_session_via_local_codex(self, *, alias: str, seed_message: str) -> str:
        start_ts = time.time()
        try:
            if str(self.repo_root) not in sys.path:
                sys.path.insert(0, str(self.repo_root))
            from task_dashboard.adapters.codex_adapter import CodexAdapter
        except Exception as e:
            _die(f"导入 CodexAdapter 失败，无法执行 fallback: {e}")

        try:
            cli_home = CodexAdapter.get_home_path()
            tmp_dir = cli_home / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out_path = tmp_dir / f"task-dashboard-bootstrap-new-session-{int(start_ts)}.last.txt"
            cmd = CodexAdapter.build_create_command(seed_prompt=seed_message, output_path=out_path)
        except Exception as e:
            _die(f"构建 Codex 建会话命令失败: {e}")

        channel_root = getattr(self, "channel_root", None)
        run_cwd = (
            channel_root
            if isinstance(channel_root, Path) and channel_root.exists() and channel_root.is_dir()
            else Path(self.desktop_cwd)
        )
        if not (run_cwd.exists() and run_cwd.is_dir()):
            run_cwd = self.repo_root

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(run_cwd),
                capture_output=True,
                text=True,
                timeout=max(10, int(self.args.session_create_timeout_s)),
            )
        except subprocess.TimeoutExpired:
            _die(f"Codex 本地建会话超时（>{int(self.args.session_create_timeout_s)}s）")
        except Exception as e:
            _die(f"Codex 本地建会话启动失败: {e}")

        sid, _spath = CodexAdapter.find_new_session_id(start_ts)
        if proc.returncode != 0:
            err = (proc.stderr or "").strip() or (proc.stdout or "").strip()
            _die(f"Codex 本地建会话失败 code={proc.returncode}: {err}")
        if not sid:
            sid = str(
                CodexAdapter.extract_session_id_from_output(
                    "\n".join(part for part in [proc.stdout, proc.stderr] if part)
                )
                or ""
            ).strip()
        if not sid:
            _die("Codex 本地建会话后未检测到 sessionId（CLI 返回成功但未发现新会话文件）")

        self._append_project_session_store_local(
            session_id=sid,
            alias=alias,
            cli_type="codex",
            channel_name=self.names.channel_dir_name,
        )
        return sid

    def _append_project_session_store_local(
        self,
        *,
        session_id: str,
        alias: str,
        cli_type: str,
        channel_name: str,
    ) -> None:
        target_paths = self._iter_project_session_store_paths()
        now = _utc_now_iso()
        channel_root_value = getattr(self, "channel_root", None)
        channel_root = (
            channel_root_value
            if isinstance(channel_root_value, Path)
            else Path(
                str(channel_root_value or getattr(self, "desktop_cwd", "") or getattr(self, "repo_root", "") or ".")
            )
        )
        workdir = str(channel_root.resolve()) if channel_root.exists() else str(channel_root)
        worktree_root = str(getattr(self, "desktop_cwd", "") or getattr(self, "repo_root", "") or "")
        names = getattr(self, "names", None)
        effective_alias = str(alias or getattr(names, "session_title", "") or channel_name or "").strip()
        effective_purpose = f"{channel_name} 主会话" if channel_name else "新建通道主会话"
        for project_path in target_paths:
            project_path.parent.mkdir(parents=True, exist_ok=True)
            data = _read_json(project_path, {})
            if not isinstance(data, dict):
                data = {}
            sessions = data.get("sessions")
            if not isinstance(sessions, list):
                sessions = []

            updated = False
            for sess in sessions:
                if not isinstance(sess, dict):
                    continue
                same_channel = str(sess.get("channel_name") or "").strip() == channel_name
                is_target_session = str(sess.get("id") or "").strip() == session_id
                if same_channel and not is_target_session:
                    sess["is_primary"] = False
                    sess["session_role"] = "child"
                if not is_target_session:
                    continue
                sess["cli_type"] = str(cli_type or sess.get("cli_type") or "codex")
                sess["alias"] = str(effective_alias or sess.get("alias") or "")
                sess["agent_name"] = str(sess.get("agent_name") or effective_alias or "")
                sess["channel_name"] = str(channel_name or sess.get("channel_name") or "")
                sess["status"] = str(sess.get("status") or "active")
                sess["environment"] = str(sess.get("environment") or "stable")
                sess["worktree_root"] = str(sess.get("worktree_root") or worktree_root)
                sess["workdir"] = str(sess.get("workdir") or workdir)
                sess["session_role"] = "primary"
                sess["purpose"] = str(sess.get("purpose") or effective_purpose)
                sess["schema_version"] = str(sess.get("schema_version") or "session.create.v2")
                sess["created_via"] = str(sess.get("created_via") or "bootstrap.local_fallback")
                sess["context_binding_state"] = str(sess.get("context_binding_state") or "bound")
                sess["is_primary"] = True
                sess["is_deleted"] = False
                sess["deleted_at"] = str(sess.get("deleted_at") or "")
                sess["deleted_reason"] = str(sess.get("deleted_reason") or "")
                sess["last_used_at"] = now
                updated = True

            if not updated:
                sessions.append(
                    {
                        "id": session_id,
                        "cli_type": str(cli_type or "codex"),
                        "alias": effective_alias,
                        "agent_name": effective_alias,
                        "model": "",
                        "reasoning_effort": "",
                        "codebuddy_permission_mode": "default",
                        "claude_permission_mode": "",
                        "environment": "stable",
                        "worktree_root": worktree_root,
                        "workdir": workdir,
                        "branch": "",
                        "session_role": "primary",
                        "purpose": effective_purpose,
                        "reuse_strategy": "",
                        "schema_version": "session.create.v2",
                        "created_via": "bootstrap.local_fallback",
                        "context_binding_state": "bound",
                        "project_execution_context": {},
                        "channel_name": str(channel_name or ""),
                        "status": "active",
                        "is_primary": True,
                        "is_deleted": False,
                        "deleted_at": "",
                        "deleted_reason": "",
                        "created_at": now,
                        "last_used_at": now,
                    }
                )
            data["project_id"] = self.project_id
            data["sessions"] = sessions
            _write_text(project_path, _json_dumps(data) + "\n")

        if self.runtime_sessions_project_path and self.runtime_sessions_project_path != self.sessions_project_path:
            _info(f"fallback 会话已同步写入 live session 真源: {self.runtime_sessions_project_path}")

    def _desktopize_session(self, session_id: str) -> None:
        _info("执行 Codex App 可见性补录（desktopize_taskboard_session.py）")
        cmd = [
            sys.executable,
            str(self.desktopize_script),
            "--session-id",
            session_id,
            "--desktop-cwd",
            self.desktop_cwd,
            "--title",
            self.names.session_title,
        ]
        for attempt in range(1, DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS + 1):
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
            if proc.returncode == 0:
                if proc.stdout.strip():
                    _info(f"desktopize_taskboard_session 输出: {proc.stdout.strip()}")
                return
            if _desktopize_session_file_missing(proc.stdout, proc.stderr):
                if attempt < DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS:
                    _warn(
                        "desktopize_taskboard_session 未发现 session 文件，"
                        f"{DESKTOPIZE_SESSION_FILE_RETRY_DELAY_S:.0f}s 后重试 "
                        f"({attempt}/{DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS})"
                    )
                    time.sleep(DESKTOPIZE_SESSION_FILE_RETRY_DELAY_S)
                    continue
                msg = (
                    "desktopize_taskboard_session 未发现 session 文件，"
                    "已降级跳过 Codex App 可见性补录；"
                    "通道创建主链继续。"
                )
                self._warnings.append(msg)
                _warn(msg)
                return
            raise_text = (
                f"desktopize_taskboard_session 失败（exit={proc.returncode}）\n"
                f"CMD: {' '.join(cmd)}\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            _die(raise_text)

    def _send_init_message(self, session_id: str) -> tuple[str, str]:
        _info("发送初始化消息（CCB announce）")
        run_id = self._announce_and_get_run_id(
            session_id=session_id,
            message=self._build_init_announce_message(),
        )
        st, _ = self._wait_run_done(run_id, expect_ok=False)
        return run_id, st

    def _send_ok_check(self, session_id: str) -> tuple[str, str, str]:
        _info("发送 OK 连通性验收消息")
        run_id = self._announce_and_get_run_id(session_id=session_id, message="仅回复 OK（连通性验收）")
        st, detail = self._wait_run_done(run_id, expect_ok=True)
        last = str(detail.get("lastMessage") or "").strip()
        return run_id, st, last

    def _send_training_message(self, session_id: str) -> str:
        _info("发送 Agent 启动培训消息")
        return self._announce_and_get_run_id(
            session_id=session_id,
            message=self._build_training_message(session_id),
        )

    def _announce_and_get_run_id(self, *, session_id: str, message: str) -> str:
        payload = {
            "projectId": self.project_id,
            "channelName": self.names.channel_dir_name,
            "sessionId": session_id,
            "message": message,
            "senderType": "human",
            "senderId": "bootstrap-script",
            "senderName": "BootstrapScript",
        }
        resp = _http_request_json(
            method="POST",
            url=f"{self.base_url}/api/codex/announce",
            payload=payload,
            token=self.token,
            timeout_s=30,
        )
        run = resp.get("run") if isinstance(resp, dict) else None
        if not isinstance(run, dict):
            _die(f"announce 返回无 run: {_json_dumps(resp)}")
        run_id = str(run.get("id") or "").strip()
        if not run_id:
            _die(f"announce 返回 run.id 为空: {_json_dumps(resp)}")
        _info(f"已入队 run: {run_id}")
        return run_id

    def _wait_run_done(self, run_id: str, *, expect_ok: bool) -> tuple[str, dict[str, Any]]:
        timeout_s = int(self.args.run_wait_timeout_s)
        interval = float(self.args.poll_interval_s)
        deadline = time.time() + timeout_s
        last_status = ""
        while time.time() < deadline:
            detail = _http_request_json(
                method="GET",
                url=f"{self.base_url}/api/codex/run/{run_id}",
                token=self.token,
                timeout_s=20,
            )
            run = detail.get("run") if isinstance(detail, dict) else None
            if not isinstance(run, dict):
                _die(f"查询 run 失败（无 run 字段）: {_json_dumps(detail)}")
            st = str(run.get("status") or "").strip().lower()
            if st != last_status:
                _info(f"run {run_id} 状态: {st}")
                last_status = st
            if st in {"done", "error"}:
                if st == "error":
                    _die(f"run {run_id} 执行失败: {_json_dumps(detail)}")
                if expect_ok:
                    last = str(detail.get("lastMessage") or "").strip()
                    if last != "OK":
                        _die(f"run {run_id} 已完成但 lastMessage 不是 OK: {last!r}")
                return st, detail
            time.sleep(interval)
        _die(f"等待 run 超时: {run_id} (> {timeout_s}s)")

    def _append_inboxes(
        self,
        *,
        session_id: str,
        init_run_id: str,
        init_run_status: str,
        ok_run_id: str,
        ok_run_status: str,
        ok_last_message: str,
        training_run_id: str,
    ) -> None:
        if self.args.no_write_inbox:
            _warn("跳过收件箱留痕（--no-write-inbox）")
            return
        t = _now_local()
        lines = [
            f"- [{t}] `A02` 通道一键创建完成",
            f"  - 通道：`{self.names.channel_dir_name}`",
            f"  - 会话：`{session_id}`",
            f"  - 主任务：`{self.task_file}`",
            f"  - 初始化 run：`{init_run_id}`（{init_run_status}）",
        ]
        if ok_run_id:
            lines.append(f"  - OK 验收 run：`{ok_run_id}`（{ok_run_status}） lastMessage=`{ok_last_message}`")
        if training_run_id:
            lines.append(f"  - 启动培训 run：`{training_run_id}`")
        lines.append(f"  - 会话标题：`{self.names.session_title}`")
        lines.append("")
        block = "\n".join(lines)
        _append_text(self.channel_inbox, block)
        if self.args.write_master_inbox and self.master_inbox:
            _append_text(self.master_inbox, block)
        elif self.args.write_master_inbox and not self.master_inbox:
            self._warnings.append("未找到总控收件箱，已跳过写入")

    def _write_result_json(self, result: BootstrapResult) -> None:
        _write_text(self.result_path, _json_dumps(asdict(result)) + "\n")

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Codex-only 通道一键创建脚本（含 App 可见性补录）")
    ap.add_argument("--project-id", default="task_dashboard")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--base-url", default="", help="默认 http://127.0.0.1:<port>")
    ap.add_argument("--token", default="", help="可选；默认读取环境变量 TASK_DASHBOARD_TOKEN")

    ap.add_argument("--channel-kind", required=True)
    ap.add_argument("--channel-index", required=True, help="如 07")
    ap.add_argument("--channel-name", required=True, help="如 可视化看板")
    ap.add_argument("--channel-scope", default="", help="如 全局任务-通道-agent资源关系")
    ap.add_argument("--desc", default="", help="通道描述（写入 config.toml）")
    ap.add_argument("--task-title", required=True, help="主任务标题（不含编号）")
    ap.add_argument("--goal", default="", help="初始化消息中的当前目标")
    ap.add_argument("--session-alias", default="", help="会话 alias（可选）")
    ap.add_argument("--target-cli-type", default="", help="目标 Agent CLI 类型；gemini 时使用 Gemini 初始化降级口径")

    ap.add_argument("--desktop-cwd", default="", help="Codex App 项目 cwd（默认自动推测 Desktop 路径）")
    ap.add_argument("--session-create-timeout-s", type=int, default=180, help="本地 fallback 建会话超时")
    ap.add_argument("--api-session-timeout-s", type=int, default=90, help="/api/sessions 建会话超时，默认与后端建会话等待口径对齐")
    ap.add_argument("--run-wait-timeout-s", type=int, default=300)
    ap.add_argument("--poll-interval-s", type=float, default=2.0)

    ap.add_argument("--write-master-inbox", dest="write_master_inbox", action="store_true", default=True)
    ap.add_argument("--no-write-master-inbox", dest="write_master_inbox", action="store_false")
    ap.add_argument("--no-write-inbox", action="store_true", help="不写通道/总控收件箱")
    ap.add_argument("--no-ok-check", action="store_true", help="跳过第二条 OK 连通性验收")
    ap.add_argument("--no-training-message", action="store_true", help="跳过 Agent 启动培训消息")
    ap.add_argument("--no-desktopize", action="store_true", help="跳过 Codex App 可见性补录（不建议）")
    ap.add_argument("--skip-health-check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    bs = Bootstrapper(args)
    result = bs.run()
    print(_json_dumps(asdict(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
