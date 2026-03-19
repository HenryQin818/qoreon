from __future__ import annotations

from typing import Any


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _norm(path: Any) -> str:
    return _as_str(path).replace('\\', '/').strip()


def resolve_project_source(project: dict[str, Any]) -> dict[str, str]:
    project_root = _norm(project.get('project_root_rel'))
    task_root = _norm(project.get('task_root_rel'))
    runtime_root = _norm(project.get('runtime_root_rel'))
    candidates = [project_root, task_root, runtime_root]

    def _has(marker: str) -> bool:
        token = f'/{marker}/'
        return any(token in f'/{c.strip("/")}/' for c in candidates if c)

    if _has('sandbox_projects'):
        return {'source_kind': 'sandbox', 'source_label': 'sandbox_projects'}
    if _has('fixtures'):
        return {'source_kind': 'fixtures', 'source_label': 'fixtures'}
    if _has('.runtime'):
        return {'source_kind': 'runtime', 'source_label': '.runtime'}
    if project_root or task_root:
        return {'source_kind': 'workspace', 'source_label': 'workspace'}
    return {'source_kind': 'unknown', 'source_label': ''}
