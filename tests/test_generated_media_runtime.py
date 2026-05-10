import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from task_dashboard.runtime.run_detail_fields import (
    candidate_local_imagegen_files,
    reconcile_generated_media_for_run,
    refresh_generated_media_status,
)


class GeneratedMediaRuntimeTests(unittest.TestCase):
    def test_refresh_generated_media_status_marks_running_candidate_generating(self) -> None:
        meta = {
            "cliType": "codex",
            "status": "running",
            "startedAt": "2026-05-08T10:00:00+0800",
        }

        changed = refresh_generated_media_status(meta, extra_texts=["我会用 imagegen 生成图片。"])

        self.assertTrue(changed)
        self.assertEqual(meta.get("generated_media_status"), "generating")

    def test_refresh_generated_media_status_ignores_ordinary_run(self) -> None:
        meta = {
            "cliType": "codex",
            "status": "running",
            "startedAt": "2026-05-08T10:00:00+0800",
        }

        changed = refresh_generated_media_status(meta, extra_texts=["普通文字任务。"])

        self.assertFalse(changed)
        self.assertNotIn("generated_media_status", meta)

    def test_reconcile_copies_local_output_imagegen_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "work"
            output_dir = workdir / "output" / "imagegen"
            output_dir.mkdir(parents=True)
            (output_dir / "result.png").write_bytes(b"fake-png")
            (output_dir / "result.html").write_text("<html></html>", encoding="utf-8")

            store = server.RunStore(base / "runs")
            run = store.create_run("p", "c", "s1", "请用 imagegen 生成图片")
            run_id = str(run["id"])
            meta = store.load_meta(run_id) or {}
            meta.update(
                {
                    "status": "done",
                    "cliType": "codex",
                    "workdir": str(workdir),
                    "skills_used": ["imagegen"],
                    "startedAt": server._now_iso(),
                    "finishedAt": server._now_iso(),
                }
            )
            log_path = store._paths(run_id)["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("[stdout] imagegen fallback wrote output/imagegen/result.png\n", encoding="utf-8")

            changed = reconcile_generated_media_for_run(store, run_id, meta, log_path=log_path)

            self.assertTrue(changed)
            attachments = meta.get("attachments") or []
            generated = [item for item in attachments if item.get("source") == "generated"]
            self.assertEqual(len(generated), 2)
            self.assertTrue(any(item.get("generatedBy") == "local_imagegen_fallback" for item in generated))
            self.assertEqual(meta.get("generated_media_status"), "generated")
            self.assertEqual(meta.get("generated_media_kind"), "image")
            self.assertEqual(meta.get("generated_media_count"), 1)
            self.assertEqual(meta.get("generated_media_summary"), "已生成1张图片")

    def test_candidate_local_imagegen_files_filters_to_output_imagegen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            output_dir = workdir / "output" / "imagegen"
            output_dir.mkdir(parents=True)
            expected = output_dir / "one.png"
            expected.write_bytes(b"png")
            (workdir / "output" / "other.png").parent.mkdir(parents=True, exist_ok=True)
            (workdir / "output" / "other.png").write_bytes(b"png")

            files = candidate_local_imagegen_files(
                {
                    "workdir": str(workdir),
                    "startedAt": "",
                    "finishedAt": "",
                }
            )

            self.assertEqual(files, [expected])

    @patch.dict(os.environ, {"CCB_NO_PROGRESS_TIMEOUT_S": "5"}, clear=False)
    def test_local_imagegen_file_counts_as_no_progress_activity(self) -> None:
        class _FakeAdapter:
            @classmethod
            def supports_model(cls) -> bool:
                return False

            @classmethod
            def build_resume_command(
                cls,
                session_id: str,
                message: str,
                output_path,
                profile_label: str = "",
                model: str = "",
                reasoning_effort: str = "",
            ) -> list[str]:
                return ["fake-cli", "resume", session_id, message, str(output_path)]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self, clock: dict[str, float]) -> None:
                self.clock = clock
                self.returncode = None
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()
                self.terminate_called = 0
                self.kill_called = 0

            def poll(self):  # type: ignore[no-untyped-def]
                if float(self.clock["t"]) >= 1004.0:
                    self.returncode = 0
                return self.returncode

            def terminate(self) -> None:
                self.terminate_called += 1

            def kill(self) -> None:
                self.kill_called += 1
                self.returncode = -9

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "work"
            output_dir = workdir / "output" / "imagegen"
            output_dir.mkdir(parents=True)
            runs_dir = base / "runs"
            store = server.RunStore(runs_dir=runs_dir)
            run = store.create_run("p", "c", "s1", "请用 imagegen 生成图片")
            run_id = str(run["id"])
            meta = store.load_meta(run_id) or {}
            meta["workdir"] = str(workdir)
            store.save_meta(run_id, meta)
            fake_clock = {"t": 1000.0}
            fake_proc = _FakeProc(fake_clock)
            created = {"done": False}

            def _fake_time() -> float:
                return float(fake_clock["t"])

            def _fake_sleep(seconds: float) -> None:
                fake_clock["t"] = float(fake_clock["t"]) + max(0.0, float(seconds or 0.0))
                if fake_clock["t"] >= 1002.0 and not created["done"]:
                    (output_dir / "progress.png").write_bytes(b"png")
                    created["done"] = True

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=fake_proc):
                    with patch.object(server.time, "time", side_effect=_fake_time):
                        with patch.object(server.time, "sleep", side_effect=_fake_sleep):
                            server.run_cli_exec(store, run_id, timeout_s=60, cli_type="codex", scheduler=None)

            final_meta = store.load_meta(run_id) or {}
            self.assertEqual(final_meta.get("status"), "done")
            self.assertNotIn("timeout>no_progress", str(final_meta.get("error") or ""))
            self.assertEqual(fake_proc.terminate_called, 0)
            self.assertEqual(fake_proc.kill_called, 0)
            self.assertEqual(final_meta.get("generated_media_status"), "generated")
            self.assertTrue(final_meta.get("process_events"))


if __name__ == "__main__":
    unittest.main()
