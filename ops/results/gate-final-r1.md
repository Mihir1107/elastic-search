# Search latency benchmark

Run at 2026-09-20T21:51:40+00:00.

| setting | value |
|---|---|
| index | `emails-v2` |
| documents | 52219 |
| concurrency | 4 |
| iterations | 6 |
| rerank | False |
| requests | 300 (0 failed) |

## Client wall time (the number the gate is about)

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| wall | 300 | 120.7 | 115.5 | 207.8 | 264.8 | 310.7 |

p95 = 207.8 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.1 | 0.1 |
| embed_ms | 300 | 37.8 | 39.4 | 61.4 | 127.8 | 133.3 |
| bm25_ms | 300 | 21.5 | 19.0 | 43.3 | 59.1 | 85.8 |
| knn_ms | 300 | 21.6 | 19.6 | 43.9 | 52.7 | 71.9 |
| fuse_ms | 300 | 0.2 | 0.2 | 0.6 | 0.8 | 0.9 |
| highlight_ms | 300 | 36.1 | 20.2 | 107.9 | 155.2 | 174.0 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 117.4 | 111.0 | 202.1 | 262.0 | 308.6 |
