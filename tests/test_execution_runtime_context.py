import tempfile
import unittest
from pathlib import Path

from task_dashboard.runtime.execution_context import prepare_run_execution_context
from task_dashboard.runtime.execution_runtime import _build_callback_context_message


class ExecutionRuntimeContextTests(unittest.TestCase):
    def test_callback_context_message_uses_receipt_summary_only(self) -> None:
        meta = {
            "trigger_type": "callback_auto",
            "receipt_summary": {
                "source_channel": "主体-总控（合并与验收）",
                "callback_task": "回执并入原消息整改计划-总控对齐",
                "execution_stage": "推进",
                "conclusion": "放行",
                "progress": "B 批推进中。",
                "need_peer": "继续推进 B 批。",
                "need_confirm": "无",
            },
        }
        original = "\n".join(
            [
                "[来源通道: 主体-总控（合并与验收）]",
                "当前结论: 放行",
                "",
                "技术明细（折叠）：",
                "- 来源run: 20260319-172954-51d06cf2",
            ]
        )
        out = _build_callback_context_message(meta, original)
        self.assertIn("当前结论: 放行", out)
        self.assertIn("需要对方: 继续推进 B 批。", out)
        self.assertIn("说明: 这是系统回执的上下文摘要。", out)
        self.assertNotIn("技术明细（折叠）", out)
        self.assertNotIn("来源run:", out)

    def test_callback_context_message_keeps_raw_message_for_non_callback(self) -> None:
        original = "普通协作消息"
        out = _build_callback_context_message({"trigger_type": "manual_dispatch"}, original)
        self.assertEqual(out, original)

    def test_prepare_run_execution_context_defaults_claude_workdir_to_channel_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            channel_root = project_root / "任务规划" / "子级02"
            channel_root.mkdir(parents=True, exist_ok=True)

            prepared = prepare_run_execution_context(
                {
                    "id": "run-1",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-claude",
                },
                cli_type="claude",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda _value: "",
                session_store_cls=type(
                    "FakeStore",
                    (),
                    {
                        "__init__": lambda self, base_dir: None,
                        "get_session": lambda self, _sid: {
                            "id": "sid-claude",
                            "cli_type": "claude",
                            "workdir": str(project_root),
                        },
                    },
                ),
                derive_session_work_context=lambda *_args, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(project_root),
                    "branch": "main",
                },
                resolve_model_for_session=lambda *_args, **_kwargs: "",
                resolve_reasoning_effort_for_session=lambda *_args, **_kwargs: "",
                resolve_run_work_context=lambda meta, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(project_root),
                    "branch": "main",
                },
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: channel_root,
                project_channel_model=lambda _pid, _channel: "",
                project_channel_reasoning_effort=lambda _pid, _channel: "",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), channel_root.resolve())
            self.assertEqual(Path((prepared["meta"] or {}).get("workdir")).resolve(), channel_root.resolve())

    def test_prepare_run_execution_context_uses_session_workdir_when_claude_run_has_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            channel_root = project_root / "任务规划" / "子级02"
            channel_root.mkdir(parents=True, exist_ok=True)
            calls = {"model": 0, "reasoning": 0}

            class FakeStore:
                def __init__(self, base_dir):
                    self.base_dir = base_dir

                def get_session(self, _sid):
                    return {
                        "id": "sid-claude",
                        "cli_type": "claude",
                        "workdir": str(channel_root),
                    }

            def _derive_session_work_context(row, **_kwargs):
                return {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(row.get("workdir") or ""),
                    "branch": "main",
                }

            def _resolve_run_work_context(meta, **kwargs):
                session_context = kwargs.get("session_context") or {}
                return {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(meta.get("workdir") or session_context.get("workdir") or project_root),
                    "branch": "main",
                }

            def _unexpected_model_lookup(*_args, **_kwargs):
                calls["model"] += 1
                raise AssertionError("run-level model exists; session model lookup must not run")

            def _unexpected_reasoning_lookup(*_args, **_kwargs):
                calls["reasoning"] += 1
                raise AssertionError("run-level reasoning exists; session reasoning lookup must not run")

            prepared = prepare_run_execution_context(
                {
                    "id": "run-claude-model",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-claude",
                    "model": "claude-fable-5",
                    "reasoning_effort": "medium",
                },
                cli_type="claude",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda value: str(value or "").strip(),
                session_store_cls=FakeStore,
                derive_session_work_context=_derive_session_work_context,
                resolve_model_for_session=_unexpected_model_lookup,
                resolve_reasoning_effort_for_session=_unexpected_reasoning_lookup,
                resolve_run_work_context=_resolve_run_work_context,
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: project_root,
                project_channel_model=lambda _pid, _channel: "claude-opus-4-8",
                project_channel_reasoning_effort=lambda _pid, _channel: "high",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), channel_root.resolve())
            self.assertEqual(Path(prepared["effective_context"]["workdir"]).resolve(), channel_root.resolve())
            self.assertEqual(Path((prepared["meta"] or {}).get("workdir")).resolve(), channel_root.resolve())
            self.assertEqual(prepared["resolved_model"], "claude-fable-5")
            self.assertEqual(prepared["resolved_reasoning"], "medium")
            self.assertEqual(calls, {"model": 0, "reasoning": 0})

    def test_prepare_run_execution_context_uses_session_workdir_when_codebuddy_run_has_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            channel_root = project_root / "任务规划" / "子级02"
            channel_root.mkdir(parents=True, exist_ok=True)

            class FakeStore:
                def __init__(self, base_dir):
                    self.base_dir = base_dir

                def get_session(self, _sid):
                    return {
                        "id": "sid-codebuddy",
                        "cli_type": "codebuddy",
                        "workdir": str(channel_root),
                    }

            prepared = prepare_run_execution_context(
                {
                    "id": "run-codebuddy-model",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-codebuddy",
                    "model": "deepseek-v4-pro",
                },
                cli_type="codebuddy",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda _value: "",
                session_store_cls=FakeStore,
                derive_session_work_context=lambda row, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(row.get("workdir") or ""),
                    "branch": "main",
                },
                resolve_model_for_session=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("run-level model exists; session model lookup must not run")
                ),
                resolve_reasoning_effort_for_session=lambda *_args, **_kwargs: "",
                resolve_run_work_context=lambda meta, **kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(
                        meta.get("workdir") or (kwargs.get("session_context") or {}).get("workdir") or project_root
                    ),
                    "branch": "main",
                },
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: project_root,
                project_channel_model=lambda _pid, _channel: "",
                project_channel_reasoning_effort=lambda _pid, _channel: "",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), channel_root.resolve())
            self.assertEqual(Path(prepared["effective_context"]["workdir"]).resolve(), channel_root.resolve())
            self.assertEqual(Path((prepared["meta"] or {}).get("workdir")).resolve(), channel_root.resolve())
            self.assertEqual(prepared["resolved_model"], "deepseek-v4-pro")

    def test_prepare_run_execution_context_keeps_session_explicit_custom_workdir_when_run_has_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            channel_root = project_root / "任务规划" / "子级02"
            custom_workdir = base / "custom-explicit"
            channel_root.mkdir(parents=True, exist_ok=True)
            custom_workdir.mkdir(parents=True, exist_ok=True)

            class FakeStore:
                def __init__(self, base_dir):
                    self.base_dir = base_dir

                def get_session(self, _sid):
                    return {
                        "id": "sid-codebuddy",
                        "cli_type": "codebuddy",
                        "workdir": str(custom_workdir),
                    }

            prepared = prepare_run_execution_context(
                {
                    "id": "run-codebuddy-custom-model",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-codebuddy",
                    "model": "deepseek-v4-pro",
                },
                cli_type="codebuddy",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda _value: "",
                session_store_cls=FakeStore,
                derive_session_work_context=lambda row, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(row.get("workdir") or ""),
                    "branch": "main",
                },
                resolve_model_for_session=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("run-level model exists; session model lookup must not run")
                ),
                resolve_reasoning_effort_for_session=lambda *_args, **_kwargs: "",
                resolve_run_work_context=lambda meta, **kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(
                        meta.get("workdir") or (kwargs.get("session_context") or {}).get("workdir") or project_root
                    ),
                    "branch": "main",
                },
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: channel_root,
                project_channel_model=lambda _pid, _channel: "",
                project_channel_reasoning_effort=lambda _pid, _channel: "",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), custom_workdir.resolve())
            self.assertEqual(Path(prepared["effective_context"]["workdir"]).resolve(), custom_workdir.resolve())
            self.assertEqual(Path((prepared["meta"] or {}).get("workdir")).resolve(), custom_workdir.resolve())
            self.assertEqual(prepared["resolved_model"], "deepseek-v4-pro")

    def test_prepare_run_execution_context_channel_fallback_only_for_project_root_session_with_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            channel_root = project_root / "任务规划" / "子级02"
            channel_root.mkdir(parents=True, exist_ok=True)

            class FakeStore:
                def __init__(self, base_dir):
                    self.base_dir = base_dir

                def get_session(self, _sid):
                    return {
                        "id": "sid-codebuddy",
                        "cli_type": "codebuddy",
                        "workdir": str(project_root),
                    }

            prepared = prepare_run_execution_context(
                {
                    "id": "run-codebuddy-project-root-model",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-codebuddy",
                    "model": "deepseek-v4-pro",
                },
                cli_type="codebuddy",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda _value: "",
                session_store_cls=FakeStore,
                derive_session_work_context=lambda row, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(row.get("workdir") or ""),
                    "branch": "main",
                },
                resolve_model_for_session=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("run-level model exists; session model lookup must not run")
                ),
                resolve_reasoning_effort_for_session=lambda *_args, **_kwargs: "",
                resolve_run_work_context=lambda meta, **kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(
                        meta.get("workdir") or (kwargs.get("session_context") or {}).get("workdir") or project_root
                    ),
                    "branch": "main",
                },
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: channel_root,
                project_channel_model=lambda _pid, _channel: "",
                project_channel_reasoning_effort=lambda _pid, _channel: "",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), channel_root.resolve())
            self.assertEqual(Path(prepared["effective_context"]["workdir"]).resolve(), channel_root.resolve())
            self.assertEqual(Path((prepared["meta"] or {}).get("workdir")).resolve(), channel_root.resolve())

    def test_prepare_run_execution_context_does_not_expand_codex_run_model_workdir_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            custom_workdir = base / "custom-explicit"
            custom_workdir.mkdir(parents=True, exist_ok=True)

            class FakeStore:
                def __init__(self, base_dir):
                    self.base_dir = base_dir

                def get_session(self, _sid):
                    return {
                        "id": "sid-codex",
                        "cli_type": "codex",
                        "workdir": str(custom_workdir),
                    }

            prepared = prepare_run_execution_context(
                {
                    "id": "run-codex-model",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-codex",
                    "model": "codex-spark",
                },
                cli_type="codex",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda _value: "",
                session_store_cls=FakeStore,
                derive_session_work_context=lambda row, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(row.get("workdir") or ""),
                    "branch": "main",
                },
                resolve_model_for_session=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("run-level model exists; session model lookup must not run")
                ),
                resolve_reasoning_effort_for_session=lambda *_args, **_kwargs: "",
                resolve_run_work_context=lambda meta, **kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(
                        meta.get("workdir") or (kwargs.get("session_context") or {}).get("workdir") or project_root
                    ),
                    "branch": "main",
                },
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: custom_workdir,
                project_channel_model=lambda _pid, _channel: "",
                project_channel_reasoning_effort=lambda _pid, _channel: "",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), project_root.resolve())
            self.assertEqual(Path(prepared["effective_context"]["workdir"]).resolve(), project_root.resolve())
            self.assertEqual(Path((prepared["meta"] or {}).get("workdir")).resolve(), project_root.resolve())
            self.assertEqual(prepared["resolved_model"], "codex-spark")

    def test_prepare_run_execution_context_keeps_explicit_codebuddy_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "repo"
            channel_root = project_root / "任务规划" / "子级02"
            explicit_workdir = base / "custom"
            channel_root.mkdir(parents=True, exist_ok=True)
            explicit_workdir.mkdir(parents=True, exist_ok=True)

            prepared = prepare_run_execution_context(
                {
                    "id": "run-2",
                    "projectId": "task_dashboard",
                    "channelName": "子级02",
                    "sessionId": "sid-codebuddy",
                    "workdir": str(explicit_workdir),
                },
                cli_type="codebuddy",
                runs_parent=base,
                worktree_root=project_root,
                normalize_reasoning_effort=lambda _value: "",
                session_store_cls=type(
                    "FakeStore",
                    (),
                    {
                        "__init__": lambda self, base_dir: None,
                        "get_session": lambda self, _sid: {
                            "id": "sid-codebuddy",
                            "cli_type": "codebuddy",
                            "workdir": str(project_root),
                        },
                    },
                ),
                derive_session_work_context=lambda *_args, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(project_root),
                    "branch": "main",
                },
                resolve_model_for_session=lambda *_args, **_kwargs: "",
                resolve_reasoning_effort_for_session=lambda *_args, **_kwargs: "",
                resolve_run_work_context=lambda meta, **_kwargs: {
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(meta.get("workdir") or ""),
                    "branch": "main",
                },
                load_project_execution_context=lambda *_args, **_kwargs: {},
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: channel_root,
                project_channel_model=lambda _pid, _channel: "",
                project_channel_reasoning_effort=lambda _pid, _channel: "",
            )

            self.assertEqual(Path(prepared["run_cwd"]).resolve(), explicit_workdir.resolve())


if __name__ == "__main__":
    unittest.main()
