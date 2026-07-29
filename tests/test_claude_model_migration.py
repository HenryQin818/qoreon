import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.runtime import claude_model_migration as migration


def _hold_exclusive_lock(runtime_root: str, ready, release) -> None:
    with migration.claude_model_migration_lock(
        Path(runtime_root),
        exclusive=True,
        timeout_s=2.0,
    ):
        ready.set()
        release.wait(5.0)


class ClaudeModelMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="td-claude-opus5-migration-")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.runtime = self.base / "runtime"
        self.sessions_dir = self.runtime / ".sessions"
        self.sessions_dir.mkdir(parents=True)
        self.config = self.base / "config.toml"
        self.config.write_text(
            """
[[projects]]
id = "task_dashboard"

[[projects.channels]]
name = "子级02"
cli_type = "claude"
model = "claude-sonnet-4-6"
""".strip()
            + "\n",
            encoding="utf-8",
        )

    def _write_project(self, project_id: str, rows: list[dict]) -> Path:
        path = self.sessions_dir / f"{project_id}.json"
        path.write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "sessions": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _row(
        session_id: str,
        *,
        cli_type: str = "claude",
        model: str = "claude-opus-4-8",
        deleted: bool = False,
    ) -> dict:
        return {
            "id": session_id,
            "cli_type": cli_type,
            "model": model,
            "channel_name": f"channel-{session_id}",
            "status": "inactive" if deleted else "active",
            "is_primary": not deleted,
            "is_deleted": deleted,
        }

    def _build_manifest(self, *, config_paths: list[Path] | None = None) -> tuple[Path, dict]:
        manifest = migration.build_dry_run_manifest(
            self.runtime,
            repo_root=self.base,
            config_paths=config_paths if config_paths is not None else [self.config],
        )
        manifest_path = self.base / "manifest.json"
        migration.write_manifest(manifest_path, manifest)
        return manifest_path, manifest

    @staticmethod
    def _idle_stop_line(*_args, **_kwargs) -> dict:
        return {
            "blocked": False,
            "working_runs": [],
            "external_busy": [],
            "process_scan_error": "",
        }

    def test_dry_run_is_read_only_and_scopes_candidates_and_config(self) -> None:
        project_path = self._write_project(
            "task_dashboard",
            [
                self._row("candidate"),
                self._row("deleted", deleted=True),
                self._row("fable", model="claude-fable-5"),
                self._row("codex", cli_type="codex", model="gpt-5.4"),
            ],
        )
        before = project_path.read_bytes()
        runtime_files_before = sorted(str(path.relative_to(self.runtime)) for path in self.runtime.rglob("*"))

        manifest_path, manifest = self._build_manifest()

        totals = manifest["session_scan"]["totals"]
        self.assertEqual(totals["candidate_sessions"], 1)
        self.assertEqual(totals["deleted_legacy_opus_skipped"], 1)
        self.assertEqual(totals["other_claude_model_skipped"], 1)
        self.assertEqual(totals["other_cli_skipped"], 1)
        self.assertEqual(manifest["session_scan"]["candidates"][0]["session_id"], "candidate")
        self.assertEqual(manifest["session_scan"]["candidates"][0]["after"], "claude-opus-5")
        self.assertEqual(manifest["config_scan"]["legacy_opus_4_8_count"], 0)
        self.assertEqual(manifest["config_scan"]["claude_model_count"], 1)
        self.assertTrue(manifest["apply_allowed"])
        self.assertTrue(manifest_path.exists())
        self.assertEqual(project_path.read_bytes(), before)
        self.assertEqual(
            sorted(str(path.relative_to(self.runtime)) for path in self.runtime.rglob("*")),
            runtime_files_before,
        )
        self.assertFalse((self.runtime / ".locks").exists())

    def test_apply_verify_and_rollback_preserve_protected_rows(self) -> None:
        project_path = self._write_project(
            "task_dashboard",
            [
                self._row("candidate"),
                self._row("deleted", deleted=True),
                self._row("sonnet", model="claude-sonnet-4-6"),
            ],
        )
        manifest_path, _manifest = self._build_manifest()

        with mock.patch.object(
            migration,
            "inspect_runtime_stop_line",
            side_effect=self._idle_stop_line,
        ):
            journal = migration.apply_manifest(manifest_path)

        self.assertEqual(journal["status"], "applied")
        rows = {
            row["id"]: row
            for row in json.loads(project_path.read_text(encoding="utf-8"))["sessions"]
        }
        self.assertEqual(rows["candidate"]["model"], "claude-opus-5")
        self.assertEqual(rows["deleted"]["model"], "claude-opus-4-8")
        self.assertEqual(rows["sonnet"]["model"], "claude-sonnet-4-6")
        verified = migration.verify_manifest(manifest_path)
        self.assertTrue(verified["ok"])
        self.assertEqual(verified["remaining_active_legacy_opus_4_8"], 0)

        with mock.patch.object(
            migration,
            "inspect_runtime_stop_line",
            side_effect=self._idle_stop_line,
        ):
            rollback = migration.rollback_manifest(manifest_path)

        self.assertEqual(rollback["status"], "rolled_back")
        rows = {
            row["id"]: row
            for row in json.loads(project_path.read_text(encoding="utf-8"))["sessions"]
        }
        self.assertEqual(rows["candidate"]["model"], "claude-opus-4-8")
        self.assertEqual(rows["deleted"]["model"], "claude-opus-4-8")
        self.assertEqual(rows["sonnet"]["model"], "claude-sonnet-4-6")

    def test_apply_blocks_when_previously_missing_config_appears(self) -> None:
        project_path = self._write_project("task_dashboard", [self._row("candidate")])
        missing_config = self.base / "config.local.toml"
        manifest_path, _manifest = self._build_manifest(config_paths=[missing_config])
        missing_config.write_text(
            '[[projects.channels]]\ncli_type = "claude"\nmodel = "claude-opus-4-8"\n',
            encoding="utf-8",
        )

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            self.assertRaises(migration.ClaudeModelMigrationBlocked) as ctx,
        ):
            migration.apply_manifest(manifest_path)

        self.assertEqual(ctx.exception.code, "config_cas_mismatch")
        self.assertEqual(
            json.loads(project_path.read_text(encoding="utf-8"))["sessions"][0]["model"],
            "claude-opus-4-8",
        )

    def test_apply_blocks_on_session_cas_change(self) -> None:
        project_path = self._write_project("task_dashboard", [self._row("candidate")])
        manifest_path, _manifest = self._build_manifest()
        payload = json.loads(project_path.read_text(encoding="utf-8"))
        payload["unrelated_change"] = True
        project_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            self.assertRaises(migration.ClaudeModelMigrationBlocked) as ctx,
        ):
            migration.apply_manifest(manifest_path)

        self.assertEqual(ctx.exception.code, "session_store_cas_mismatch")

    def test_apply_current_value_guard_blocks_scope_change(self) -> None:
        project_path = self._write_project("task_dashboard", [self._row("candidate")])
        manifest_path, manifest = self._build_manifest()
        payload = json.loads(project_path.read_text(encoding="utf-8"))
        payload["sessions"][0]["model"] = "claude-sonnet-4-6"
        project_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["session_scan"]["projects"][0]["sha256_before"] = migration._sha256_path(project_path)
        migration.write_manifest(manifest_path, manifest)

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            self.assertRaises(migration.ClaudeModelMigrationBlocked) as ctx,
        ):
            migration.apply_manifest(manifest_path)

        self.assertEqual(ctx.exception.code, "candidate_value_changed")
        self.assertEqual(
            json.loads(project_path.read_text(encoding="utf-8"))["sessions"][0]["model"],
            "claude-sonnet-4-6",
        )

    def test_apply_rejects_manifest_session_path_outside_store(self) -> None:
        self._write_project("task_dashboard", [self._row("candidate")])
        manifest_path, manifest = self._build_manifest()
        outside = self.base / "outside.json"
        outside.write_text(
            json.dumps(
                {
                    "project_id": "outside",
                    "sessions": [self._row("candidate")],
                }
            ),
            encoding="utf-8",
        )
        manifest["session_scan"]["projects"][0]["file"] = str(outside)
        manifest["session_scan"]["projects"][0]["sha256_before"] = migration._sha256_path(outside)
        manifest["session_scan"]["candidates"][0]["file"] = str(outside)
        migration.write_manifest(manifest_path, manifest)

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            self.assertRaises(migration.ClaudeModelMigrationBlocked) as ctx,
        ):
            migration.apply_manifest(manifest_path)

        self.assertEqual(ctx.exception.code, "manifest_session_path_invalid")
        self.assertEqual(
            json.loads(outside.read_text(encoding="utf-8"))["sessions"][0]["model"],
            "claude-opus-4-8",
        )

    def test_apply_blocks_when_any_claude_run_is_working(self) -> None:
        project_path = self._write_project("task_dashboard", [self._row("candidate")])
        manifest_path, _manifest = self._build_manifest()
        hot = self.runtime / ".runs" / "hot"
        hot.mkdir(parents=True)
        (hot / "working.json").write_text(
            json.dumps(
                {
                    "id": "working",
                    "cliType": "claude",
                    "sessionId": "another-session",
                    "status": "queued",
                }
            ),
            encoding="utf-8",
        )

        with (
            mock.patch.object(migration, "_scan_process_table", return_value=([], "")),
            self.assertRaises(migration.ClaudeModelMigrationBlocked) as ctx,
        ):
            migration.apply_manifest(manifest_path)

        self.assertEqual(ctx.exception.code, "runtime_busy")
        self.assertEqual(
            json.loads(project_path.read_text(encoding="utf-8"))["sessions"][0]["model"],
            "claude-opus-4-8",
        )

    def test_apply_failure_compensates_completed_projects(self) -> None:
        project_a = self._write_project("project_a", [self._row("candidate-a")])
        project_b = self._write_project("project_b", [self._row("candidate-b")])
        manifest_path, _manifest = self._build_manifest()
        real_atomic_write = migration._atomic_write_json

        def fail_second_project(
            path: Path,
            payload: dict,
            *,
            on_replaced=None,
        ) -> None:
            if Path(path).resolve() == project_b.resolve():
                raise OSError("injected second project failure")
            real_atomic_write(path, payload, on_replaced=on_replaced)

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            mock.patch.object(migration, "_atomic_write_json", side_effect=fail_second_project),
            self.assertRaises(OSError),
        ):
            migration.apply_manifest(manifest_path)

        for path in (project_a, project_b):
            rows = json.loads(path.read_text(encoding="utf-8"))["sessions"]
            self.assertEqual(rows[0]["model"], "claude-opus-4-8")
        journal = json.loads(
            manifest_path.with_name(manifest_path.stem + ".journal.json").read_text(encoding="utf-8")
        )
        self.assertEqual(journal["status"], "compensated")

    def test_apply_hash_failure_after_atomic_replace_compensates_current_project(self) -> None:
        project_a = self._write_project("project_a", [self._row("candidate-a")])
        project_b = self._write_project("project_b", [self._row("candidate-b")])
        manifest_path, _manifest = self._build_manifest()
        real_sha256 = migration._sha256_path
        failure_injected = False

        def fail_second_project_after_replace(path: Path) -> str:
            nonlocal failure_injected
            resolved = Path(path).resolve()
            if resolved == project_b.resolve() and not failure_injected:
                rows = json.loads(resolved.read_text(encoding="utf-8"))["sessions"]
                if rows[0]["model"] == "claude-opus-5":
                    failure_injected = True
                    raise OSError("injected sha256_after failure")
            return real_sha256(path)

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            mock.patch.object(
                migration,
                "_sha256_path",
                side_effect=fail_second_project_after_replace,
            ),
            self.assertRaisesRegex(OSError, "injected sha256_after failure"),
        ):
            migration.apply_manifest(manifest_path)

        self.assertTrue(failure_injected)
        for path in (project_a, project_b):
            rows = json.loads(path.read_text(encoding="utf-8"))["sessions"]
            self.assertEqual(rows[0]["model"], "claude-opus-4-8")
        journal = json.loads(
            manifest_path.with_name(manifest_path.stem + ".journal.json").read_text(encoding="utf-8")
        )
        self.assertEqual(journal["status"], "compensated")
        self.assertTrue(journal["compensation_verification"]["ok"])

    def test_rollback_hash_failure_compensates_and_can_retry(self) -> None:
        project_a = self._write_project("project_a", [self._row("candidate-a")])
        project_b = self._write_project("project_b", [self._row("candidate-b")])
        manifest_path, _manifest = self._build_manifest()
        with mock.patch.object(
            migration,
            "inspect_runtime_stop_line",
            side_effect=self._idle_stop_line,
        ):
            migration.apply_manifest(manifest_path)

        real_sha256 = migration._sha256_path
        failure_injected = False

        def fail_second_project_after_rollback_replace(path: Path) -> str:
            nonlocal failure_injected
            resolved = Path(path).resolve()
            if resolved == project_b.resolve() and not failure_injected:
                rows = json.loads(resolved.read_text(encoding="utf-8"))["sessions"]
                if rows[0]["model"] == "claude-opus-4-8":
                    failure_injected = True
                    raise OSError("injected sha256_rollback failure")
            return real_sha256(path)

        with (
            mock.patch.object(
                migration,
                "inspect_runtime_stop_line",
                side_effect=self._idle_stop_line,
            ),
            mock.patch.object(
                migration,
                "_sha256_path",
                side_effect=fail_second_project_after_rollback_replace,
            ),
            self.assertRaisesRegex(OSError, "injected sha256_rollback failure"),
        ):
            migration.rollback_manifest(manifest_path)

        self.assertTrue(failure_injected)
        for path in (project_a, project_b):
            rows = json.loads(path.read_text(encoding="utf-8"))["sessions"]
            self.assertEqual(rows[0]["model"], "claude-opus-5")
        journal_path = manifest_path.with_name(manifest_path.stem + ".journal.json")
        compensated = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(compensated["status"], "rollback_compensated")
        self.assertTrue(compensated["rollback_compensation_verification"]["ok"])

        with mock.patch.object(
            migration,
            "inspect_runtime_stop_line",
            side_effect=self._idle_stop_line,
        ):
            rolled_back = migration.rollback_manifest(manifest_path)

        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual(rolled_back["rollback_attempt"], 2)
        self.assertNotIn("rollback_error", rolled_back)
        self.assertNotIn("rollback_compensation_failures", rolled_back)
        for path in (project_a, project_b):
            rows = json.loads(path.read_text(encoding="utf-8"))["sessions"]
            self.assertEqual(rows[0]["model"], "claude-opus-4-8")

    def test_verify_detects_active_legacy_session_added_after_apply(self) -> None:
        self._write_project("task_dashboard", [self._row("candidate")])
        manifest_path, _manifest = self._build_manifest()
        with mock.patch.object(
            migration,
            "inspect_runtime_stop_line",
            side_effect=self._idle_stop_line,
        ):
            migration.apply_manifest(manifest_path)
        extra_path = self._write_project("late_project", [self._row("late-candidate")])

        with self.assertRaises(migration.ClaudeModelMigrationError) as ctx:
            migration.verify_manifest(manifest_path)

        self.assertEqual(ctx.exception.code, "migration_verify_failed")
        self.assertEqual(
            ctx.exception.details["remaining_active_legacy_opus_4_8"],
            1,
        )
        extra_path.unlink()

    def test_exclusive_lock_blocks_concurrent_shared_writer(self) -> None:
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        release = ctx.Event()
        process = ctx.Process(
            target=_hold_exclusive_lock,
            args=(str(self.runtime), ready, release),
        )
        process.start()
        self.addCleanup(lambda: process.terminate() if process.is_alive() else None)
        self.assertTrue(ready.wait(3.0))
        try:
            with self.assertRaises(migration.ClaudeModelMigrationBlocked) as caught:
                with migration.claude_model_migration_lock(
                    self.runtime,
                    exclusive=False,
                    timeout_s=0.05,
                ):
                    pass
            self.assertEqual(caught.exception.code, "migration_lock_timeout")
        finally:
            release.set()
            process.join(timeout=3.0)
        self.assertEqual(process.exitcode, 0)


if __name__ == "__main__":
    unittest.main()
