# Search latency benchmark

Run at 2026-09-20T19:43:32+00:00.

| setting | value |
|---|---|
| index | `emails-v2` |
| documents | 52219 |
| concurrency | 8 |
| iterations | 4 |
| rerank | False |
| requests | 200 (0 failed) |

## Client wall time (the number the gate is about)

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| wall | 200 | 144.6 | 139.3 | 254.6 | 303.7 | 310.3 |

p95 = 254.6 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 200 | 0.0 | 0.0 | 0.0 | 0.1 | 0.1 |
| embed_ms | 200 | 64.5 | 71.1 | 104.6 | 124.5 | 130.6 |
| bm25_ms | 200 | 55.7 | 31.4 | 149.5 | 198.7 | 203.9 |
| knn_ms | 200 | 20.8 | 17.4 | 51.3 | 83.5 | 104.8 |
| fuse_ms | 200 | 0.1 | 0.1 | 0.2 | 0.4 | 0.8 |
| rerank_ms | 200 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 200 | 141.3 | 133.9 | 252.6 | 301.6 | 307.4 |
