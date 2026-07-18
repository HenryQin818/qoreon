# -*- coding: utf-8 -*-
"""HTTP adapters for project resource list APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from task_dashboard.runtime.project_resources import ProjectResourceStore

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def _store(ctx: Any) -> ProjectResourceStore:
    return ProjectResourceStore(
        getattr(ctx, "worktree_root", "."),
        environment_name=str(getattr(ctx, "environment_name", "stable") or "stable"),
    )


def _decode_path_segment(value: str) -> str:
    return unquote(str(value or "")).strip()


def handle_project_resources_get(
    ctx: Any,
    handler: "BaseHTTPRequestHandler",
    project_id: str,
) -> None:
    payload = _store(ctx).list(_decode_path_segment(project_id))
    ctx.json_response(handler, 200, payload)


def handle_project_resources_post(
    ctx: Any,
    handler: "BaseHTTPRequestHandler",
    project_id: str,
) -> None:
    if not ctx.require_token():
        return
    try:
        body = ctx.read_body_json(handler, max_bytes=30_000)
    except Exception as exc:
        ctx.json_response(handler, 400, {"error": f"bad json: {exc}"})
        return
    try:
        item = _store(ctx).create(_decode_path_segment(project_id), body)
    except ValueError as exc:
        ctx.json_response(handler, 400, {"error": str(exc)})
        return
    except Exception as exc:
        ctx.json_response(handler, 500, {"error": f"save resource failed: {exc}"})
        return
    ctx.json_response(handler, 200, {"ok": True, "item": item})


def handle_project_resources_patch(
    ctx: Any,
    handler: "BaseHTTPRequestHandler",
    project_id: str,
    resource_id: str,
) -> None:
    if not ctx.require_token():
        return
    try:
        body = ctx.read_body_json(handler, max_bytes=30_000)
    except Exception as exc:
        ctx.json_response(handler, 400, {"error": f"bad json: {exc}"})
        return
    try:
        item = _store(ctx).update(_decode_path_segment(project_id), _decode_path_segment(resource_id), body)
    except ValueError as exc:
        ctx.json_response(handler, 400, {"error": str(exc)})
        return
    except Exception as exc:
        ctx.json_response(handler, 500, {"error": f"update resource failed: {exc}"})
        return
    if item is None:
        ctx.json_response(handler, 404, {"error": "resource not found"})
        return
    ctx.json_response(handler, 200, {"ok": True, "item": item})


def handle_project_resources_delete(
    ctx: Any,
    handler: "BaseHTTPRequestHandler",
    project_id: str,
    resource_id: str,
) -> None:
    if not ctx.require_token():
        return
    try:
        deleted, count = _store(ctx).delete(_decode_path_segment(project_id), _decode_path_segment(resource_id))
    except Exception as exc:
        ctx.json_response(handler, 500, {"error": f"delete resource failed: {exc}"})
        return
    if not deleted:
        ctx.json_response(handler, 404, {"error": "resource not found", "deleted": False, "count": int(count)})
        return
    ctx.json_response(handler, 200, {"ok": True, "deleted": True, "count": int(count)})
