from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    project_id: str
    project_name: str
    channel: str
    status: str
    type: str
    title: str
    code: str
    path: str
    updated_at: str
    owner: str
    due: str
    excerpt: str
    tags: list[str]

