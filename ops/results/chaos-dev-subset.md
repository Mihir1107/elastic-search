# Chaos run — single node killed under live load

Run at 2026-09-20T17:55:43+00:00. Killed `elastic-search-es01-1` with `docker kill` (SIGKILL, not a graceful stop).

## Gate: **MET** — 0 failed requests

2308 requests at concurrency 4, 100.00% successful.

## Latency by phase

| phase | requests | failed | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|
| before | 145 | 0 | 130.5 | 298.2 | 391.1 |
| during | 1516 | 0 | 82.7 | 176.1 | 213.9 |
| after | 632 | 0 | 102.4 | 226.7 | 285.7 |

## Timeline

| t | event |
|---:|---|
| 0.0s | green |
| 15.4s | docker kill elastic-search-es01-1 |
| 16.6s | yellow |
| 50.6s | docker start elastic-search-es01-1 |
| 68.6s | green |
| 68.6s | cluster returned to green |

## Replica promotion

Shards that were replicas before the kill and primaries during it: `emails-v1/0`, `emails-v1/1`

### Before the kill

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | replica | STARTED | es02 |
| emails-v1 | 0 | primary | STARTED | es01 |
| emails-v1 | 1 | replica | STARTED | es03 |
| emails-v1 | 1 | primary | STARTED | es01 |
| emails-v1 | 2 | replica | STARTED | es02 |
| emails-v1 | 2 | primary | STARTED | es03 |

### While the node was down

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | UNASSIGNED | — |
| emails-v1 | 1 | primary | STARTED | es03 |
| emails-v1 | 1 | replica | UNASSIGNED | — |
| emails-v1 | 2 | primary | STARTED | es03 |
| emails-v1 | 2 | replica | STARTED | es02 |

### After recovery

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | primary | STARTED | es03 |
| emails-v1 | 1 | replica | STARTED | es01 |
| emails-v1 | 2 | primary | STARTED | es03 |
| emails-v1 | 2 | replica | STARTED | es02 |
