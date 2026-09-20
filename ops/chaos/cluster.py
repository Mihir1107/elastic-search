"""Cluster observation + the docker actions the chaos run takes.

Health is polled against *every* published node and the first answer wins:
during the run one of them is deliberately dead, so a poller pinned to a single
node would stop reporting exactly when the report needs it most.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class HealthSample:
    at: float
    status: str
    nodes: int
    active_shards: int
    unassigned_shards: int
    relocating_shards: int
    initializing_shards: int
    error: str | None = None


@dataclass
class ClusterWatcher:
    hosts: list[str]
    username: str
    password: str
    ca_cert: str
    timeout_s: float = 5.0
    samples: list[HealthSample] = field(default_factory=list)

    def _client(self, host: str) -> httpx.Client:
        return httpx.Client(
            base_url=host,
            auth=(self.username, self.password),
            verify=self.ca_cert,
            timeout=self.timeout_s,
        )

    def _get(self, path: str) -> Any:
        """First node that answers. Returns None when the whole cluster is silent.

        Typed ``Any`` because ``_cluster/health`` answers with an object and
        ``_cat/shards`` with an array; each caller guards the shape it wants.
        """
        for host in self.hosts:
            try:
                with self._client(host) as client:
                    response = client.get(path)
                    if response.status_code == 200:
                        return response.json()
            except (httpx.HTTPError, OSError):
                continue
        return None

    def poll(self) -> HealthSample:
        body = self._get("/_cluster/health")
        at = time.monotonic()
        if not isinstance(body, dict):
            return HealthSample(at, "unreachable", 0, 0, 0, 0, 0, error="no-node-answered")
        sample = HealthSample(
            at=at,
            status=str(body.get("status", "?")),
            nodes=int(body.get("number_of_nodes", 0)),
            active_shards=int(body.get("active_shards", 0)),
            unassigned_shards=int(body.get("unassigned_shards", 0)),
            relocating_shards=int(body.get("relocating_shards", 0)),
            initializing_shards=int(body.get("initializing_shards", 0)),
        )
        self.samples.append(sample)
        return sample

    def shards(self, index_pattern: str) -> list[dict[str, str]]:
        """``_cat/shards`` rows -- the evidence that a replica was promoted."""
        cols = "index,shard,prirep,state,node"
        body = self._get(f"/_cat/shards/{index_pattern}?format=json&h={cols}")
        if not isinstance(body, list):
            return []
        # An unassigned shard reports a null node; keep that as "" so callers
        # can test it falsily instead of against the string "None".
        return [{str(k): ("" if v is None else str(v)) for k, v in row.items()} for row in body]

    def transitions(self) -> list[tuple[float, str]]:
        """Collapse the health poll into the status changes worth printing."""
        changes: list[tuple[float, str]] = []
        for sample in self.samples:
            if not changes or changes[-1][1] != sample.status:
                changes.append((sample.at, sample.status))
        return changes


def docker(*args: str) -> str:
    """Run a docker command, raising with its stderr so a failure is not silent."""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, timeout=120
    )
    if result.returncode != 0:
        msg = f"docker {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def container_for_node(node: str) -> str:
    """Map an Elasticsearch node name to the container running it."""
    names = docker("ps", "--format", "{{.Names}}").splitlines()
    matches = [n for n in names if node in n]
    if not matches:
        msg = f"no running container matches node {node!r} (running: {names})"
        raise RuntimeError(msg)
    return matches[0]


def busiest_primary_node(rows: list[dict[str, str]]) -> str:
    """The node holding the most primaries -- the one worth killing.

    Killing a node that happens to hold only replicas costs the cluster nothing
    to recover from and demonstrates no promotion, which is most of what the HA
    gate is asking to see.
    """
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("prirep") == "p" and row.get("node"):
            counts[row["node"]] = counts.get(row["node"], 0) + 1
    if not counts:
        msg = "no started primaries found; is the index allocated?"
        raise RuntimeError(msg)
    return max(sorted(counts), key=lambda node: counts[node])
