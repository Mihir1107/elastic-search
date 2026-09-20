# Search latency benchmark

Run at 2026-09-20T17:44:55+00:00.

| setting | value |
|---|---|
| index | `emails-v1` |
| documents | 7355 |
| concurrency | 4 |
| iterations | 4 |
| rerank | False |
| requests | 200 (0 failed) |

## Client wall time (the number the gate is about)

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| wall | 200 | 155.1 | 125.8 | 301.4 | 617.0 | 752.4 |

p95 = 301.4 ms against a 300 ms target: **NOT MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 200 | 0.0 | 0.0 | 0.0 | 0.1 | 0.2 |
| embed_ms | 200 | 17.9 | 18.3 | 30.2 | 49.2 | 69.6 |
| bm25_ms | 200 | 91.6 | 64.5 | 234.0 | 438.8 | 549.1 |
| knn_ms | 200 | 37.5 | 33.4 | 91.8 | 154.9 | 213.0 |
| fuse_ms | 200 | 0.1 | 0.1 | 0.2 | 0.6 | 1.6 |
| rerank_ms | 200 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 200 | 147.3 | 117.6 | 295.8 | 542.8 | 734.1 |
