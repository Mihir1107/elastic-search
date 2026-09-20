# Chaos run — single node killed under live load

Run at 2026-09-20T21:53:34+00:00. Killed `elastic-search-es03-1` with `docker kill` (SIGKILL, not a graceful stop).

## Gate: **MET** — 0 failed requests

2802 requests at concurrency 4, 100.00% successful.

## Latency by phase

| phase | requests | failed | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|
| before | 709 | 0 | 101.8 | 197.8 | 232.5 |
| during | 1425 | 0 | 100.5 | 203.1 | 240.8 |
| after | 637 | 0 | 151.0 | 364.4 | 670.4 |

## Timeline

| t | event |
|---:|---|
| 0.0s | green |
| 20.5s | docker kill elastic-search-es03-1 |
| 21.3s | yellow |
| 60.9s | docker start elastic-search-es03-1 |
| 88.4s | green |
| 88.9s | cluster returned to green |

## Replica promotion

Shards that were replicas before the kill and primaries during it: `emails-v1/1`, `emails-v1/2`, `emails-v2/2`

### Before the kill

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | replica | STARTED | es02 |
| emails-v1 | 1 | primary | STARTED | es03 |
| emails-v1 | 2 | primary | STARTED | es03 |
| emails-v1 | 2 | replica | STARTED | es01 |
| emails-v2 | 0 | primary | STARTED | es02 |
| emails-v2 | 0 | replica | STARTED | es01 |
| emails-v2 | 1 | replica | STARTED | es03 |
| emails-v2 | 1 | primary | STARTED | es01 |
| emails-v2 | 2 | replica | STARTED | es02 |
| emails-v2 | 2 | primary | STARTED | es03 |

### While the node was down

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | primary | STARTED | es02 |
| emails-v1 | 1 | replica | UNASSIGNED | — |
| emails-v1 | 2 | primary | STARTED | es01 |
| emails-v1 | 2 | replica | UNASSIGNED | — |
| emails-v2 | 0 | primary | STARTED | es02 |
| emails-v2 | 0 | replica | STARTED | es01 |
| emails-v2 | 1 | primary | STARTED | es01 |
| emails-v2 | 1 | replica | UNASSIGNED | — |
| emails-v2 | 2 | primary | STARTED | es02 |
| emails-v2 | 2 | replica | UNASSIGNED | — |

### After recovery

| index | shard | role | state | node |
|---|---:|---|---|---|
| emails-v1 | 0 | primary | STARTED | es02 |
| emails-v1 | 0 | replica | STARTED | es01 |
| emails-v1 | 1 | primary | STARTED | es02 |
| emails-v1 | 1 | replica | RELOCATING | es01 -> 172.20.0.4 28i-FgckRyOAroPf2MQ-Ag es03 |
| emails-v1 | 2 | replica | RELOCATING | es02 -> 172.20.0.4 28i-FgckRyOAroPf2MQ-Ag es03 |
| emails-v1 | 2 | primary | STARTED | es01 |
| emails-v2 | 0 | primary | STARTED | es02 |
| emails-v2 | 0 | replica | STARTED | es01 |
| emails-v2 | 1 | replica | STARTED | es02 |
| emails-v2 | 1 | primary | STARTED | es01 |
| emails-v2 | 2 | primary | STARTED | es02 |
| emails-v2 | 2 | replica | STARTED | es01 |
