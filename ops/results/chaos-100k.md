# Chaos run — single node killed under live load

Run at 2026-09-20T19:52:11+00:00. Killed `elastic-search-es03-1` with `docker kill` (SIGKILL, not a graceful stop).

## Gate: **MET** — 0 failed requests

3654 requests at concurrency 4, 100.00% successful.

## Latency by phase

| phase | requests | failed | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|
| before | 1012 | 0 | 67.4 | 156.2 | 178.3 |
| during | 1883 | 0 | 72.1 | 172.9 | 202.1 |
| after | 732 | 0 | 118.3 | 337.4 | 840.0 |

## Timeline

| t | event |
|---:|---|
| 0.0s | green |
| 20.3s | docker kill elastic-search-es03-1 |
| 21.7s | yellow |
| 60.6s | docker start elastic-search-es03-1 |
| 87.7s | green |
| 88.6s | cluster returned to green |

## Replica promotion

Shards that were replicas before the kill and primaries during it: `emails-v1/1`, `emails-v1/2`, `emails-v2/2`

### Before the kill

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | primary | STARTED | es03 |
| emails-v1 | 1 | replica | STARTED | es01 |
| emails-v1 | 2 | primary | STARTED | es03 |
| emails-v1 | 2 | replica | STARTED | es02 |
| emails-v2 | 0 | replica | STARTED | es03 |
| emails-v2 | 0 | primary | STARTED | es02 |
| emails-v2 | 1 | replica | STARTED | es02 |
| emails-v2 | 1 | primary | STARTED | es01 |
| emails-v2 | 2 | primary | STARTED | es03 |
| emails-v2 | 2 | replica | STARTED | es01 |

### While the node was down

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | primary | STARTED | es01 |
| emails-v1 | 1 | replica | UNASSIGNED | — |
| emails-v1 | 2 | primary | STARTED | es02 |
| emails-v1 | 2 | replica | UNASSIGNED | — |
| emails-v2 | 0 | primary | STARTED | es02 |
| emails-v2 | 0 | replica | UNASSIGNED | — |
| emails-v2 | 1 | replica | STARTED | es02 |
| emails-v2 | 1 | primary | STARTED | es01 |
| emails-v2 | 2 | primary | STARTED | es01 |
| emails-v2 | 2 | replica | UNASSIGNED | — |

### After recovery

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | replica | STARTED | es02 |
| emails-v1 | 1 | primary | STARTED | es01 |
| emails-v1 | 2 | primary | STARTED | es02 |
| emails-v1 | 2 | replica | STARTED | es01 |
| emails-v2 | 0 | primary | STARTED | es02 |
| emails-v2 | 0 | replica | STARTED | es01 |
| emails-v2 | 1 | replica | STARTED | es02 |
| emails-v2 | 1 | primary | STARTED | es01 |
| emails-v2 | 2 | replica | STARTED | es02 |
| emails-v2 | 2 | primary | STARTED | es01 |
