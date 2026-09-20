"""Register a filesystem repository, snapshot the live index, restore to a new one.

The compose file mounts one ``snapshots`` volume on every node and sets
``path.repo=/snapshots``, which a shared filesystem repository requires: each
node writes its own shards, so the location must be visible to all of them.
Ref: elastic.co/docs/deploy-manage/tools/snapshot-and-restore/shared-file-system-repository

Restore never touches the serving index. It renames into a new index version and
leaves aliases behind (``include_aliases=False``), so ``emails`` keeps pointing
where it pointed until somebody flips it deliberately.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from elasticsearch import Elasticsearch

#: Matches the versioned index names the ingest writes: emails-v1, emails-v2, ...
VERSIONED = re.compile(r"^(?P<base>.+)-v(?P<version>\d+)$")


@dataclass(frozen=True)
class SnapshotInfo:
    name: str
    state: str
    indices: list[str]
    shards_total: int
    shards_failed: int
    duration_ms: int


def ensure_repository(es: Elasticsearch, name: str, location: str) -> bool:
    """Register the repository if it is not already there. Returns True if created."""
    existing = es.snapshot.get_repository(name="*").body
    if name in existing:
        return False
    es.snapshot.create_repository(
        name=name, repository={"type": "fs", "settings": {"location": location}}
    )
    return True


def resolve_alias(es: Elasticsearch, alias: str) -> str:
    """The one concrete index behind ``alias``."""
    body = es.indices.get_alias(name=alias).body
    names = sorted(body)
    if len(names) != 1:
        msg = f"expected exactly one index behind alias {alias!r}, found {names}"
        raise RuntimeError(msg)
    return str(names[0])


def next_version(index: str, existing: list[str]) -> str:
    """``emails-v1`` -> ``emails-v2``, skipping any version already present."""
    match = VERSIONED.match(index)
    if not match:
        msg = f"index {index!r} is not versioned (expected a -vN suffix)"
        raise ValueError(msg)
    base, version = match.group("base"), int(match.group("version"))
    taken = set(existing)
    version += 1
    while f"{base}-v{version}" in taken:
        version += 1
    return f"{base}-v{version}"


def create(es: Elasticsearch, repository: str, snapshot: str, indices: str) -> SnapshotInfo:
    """Take a snapshot and wait for it, so a failure is visible here not later."""
    es.snapshot.create(
        repository=repository,
        snapshot=snapshot,
        indices=indices,
        include_global_state=False,
        wait_for_completion=True,
    )
    body = es.snapshot.get(repository=repository, snapshot=snapshot).body
    detail: dict[str, Any] = body["snapshots"][0]
    shards = detail.get("shards", {})
    return SnapshotInfo(
        name=detail["snapshot"],
        state=detail["state"],
        indices=list(detail.get("indices", [])),
        shards_total=int(shards.get("total", 0)),
        shards_failed=int(shards.get("failed", 0)),
        duration_ms=int(detail.get("duration_in_millis", 0)),
    )


def restore_as(
    es: Elasticsearch,
    repository: str,
    snapshot: str,
    source_index: str,
    target_index: str,
    *,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Restore ``source_index`` under a new name. Refuses to overwrite anything."""
    if es.indices.exists(index=target_index):
        msg = f"target index {target_index!r} already exists; refusing to restore over it"
        raise RuntimeError(msg)

    es.snapshot.restore(
        repository=repository,
        snapshot=snapshot,
        indices=source_index,
        rename_pattern=re.escape(source_index),
        rename_replacement=target_index,
        # The alias must not ride along: restoring it would repoint `emails` at
        # an index that has not been verified yet.
        include_aliases=False,
        include_global_state=False,
        wait_for_completion=True,
    )

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        health = es.cluster.health(index=target_index, wait_for_status="yellow", timeout="30s").body
        if not health.get("timed_out"):
            break

    count = int(es.count(index=target_index).body["count"])
    aliases = es.indices.get_alias(index=target_index).body[target_index]["aliases"]
    return {
        "target_index": target_index,
        "docs": count,
        "aliases": sorted(aliases),
        "health": es.cluster.health(index=target_index).body["status"],
    }
