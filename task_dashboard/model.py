from __future__ import annotations

from dataclasses import dataclass, field


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
    task_id: str
    parent_task_id: str
    created_at: str
    updated_at: str
    owner: str
    due: str
    excerpt: str
    tags: list[str]
    main_owner: dict[str, str] | None = None
    collaborators: list[dict[str, str]] = field(default_factory=list)
    validators: list[dict[str, str]] = field(default_factory=list)
    challengers: list[dict[str, str]] = field(default_factory=list)
    backup_owners: list[dict[str, str]] = field(default_factory=list)
    management_slot: list[dict[str, str]] = field(default_factory=list)
    custom_roles: list[dict[str, str]] = field(default_factory=list)
    executors: list[dict[str, str]] = field(default_factory=list)
    acceptors: list[dict[str, str]] = field(default_factory=list)
    reviewers: list[dict[str, str]] = field(default_factory=list)
    visual_reviewers: list[dict[str, str]] = field(default_factory=list)
