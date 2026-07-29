# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any


_PROCESS_GROUP_ID_ATTR = "_task_dashboard_process_group_id"


def process_group_spawn_kwargs() -> dict[str, bool]:
    """Return Popen kwargs that isolate the CLI and all of its children."""
    return {"start_new_session": True} if os.name == "posix" else {}


def mark_process_group(proc: Any) -> None:
    """Remember the dedicated process group while its leader PID is available."""
    if os.name != "posix":
        return
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return
    try:
        setattr(proc, _PROCESS_GROUP_ID_ATTR, pid)
    except Exception:
        pass


def terminate_process_tree(
    proc: Any,
    *,
    graceful: bool = True,
    sleep_s: float = 0.25,
) -> bool:
    """Stop a dedicated CLI process group, with a direct-process fallback."""
    pgid = getattr(proc, _PROCESS_GROUP_ID_ATTR, None)
    if os.name == "posix" and isinstance(pgid, int) and pgid > 0:
        signaled = False
        if graceful:
            try:
                os.killpg(pgid, signal.SIGTERM)
                signaled = True
            except ProcessLookupError:
                return True
            except Exception:
                pass
            if signaled:
                time.sleep(max(0.0, float(sleep_s or 0.0)))
        try:
            os.killpg(pgid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return True
        except Exception:
            if signaled:
                return True

    try:
        if proc.poll() is not None:
            return True
        if graceful:
            proc.terminate()
            time.sleep(max(0.0, float(sleep_s or 0.0)))
            if proc.poll() is not None:
                return True
        proc.kill()
        return True
    except Exception:
        return False


def run_process_in_group(
    cmd: list[str],
    *,
    cwd: str,
    capture_output: bool,
    text: bool,
    timeout: float | None,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a short-lived CLI retry and always reclaim its process group."""
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        env=env,
        **process_group_spawn_kwargs(),
    )
    mark_process_group(proc)
    communicate = getattr(proc, "communicate", None)
    if not callable(communicate):
        # Compatibility for lightweight Popen fakes used by existing tests.
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            env=env,
        )
    try:
        stdout, stderr = communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        terminate_process_tree(proc, graceful=False)
        stdout, stderr = communicate()
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output=stdout if stdout is not None else exc.output,
            stderr=stderr if stderr is not None else exc.stderr,
        ) from exc
    finally:
        terminate_process_tree(proc, graceful=True, sleep_s=0.05)
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=int(proc.returncode or 0),
        stdout=stdout,
        stderr=stderr,
    )
