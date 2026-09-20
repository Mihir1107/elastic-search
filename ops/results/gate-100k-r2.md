# Search latency benchmark

Run at 2026-09-20T21:04:12+00:00.

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
| wall | 300 | 95.9 | 83.7 | 190.3 | 225.2 | 272.0 |

p95 = 190.3 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.1 | 0.1 |
| embed_ms | 300 | 31.8 | 35.0 | 56.7 | 62.9 | 68.6 |
| bm25_ms | 300 | 47.4 | 28.9 | 131.3 | 160.2 | 227.2 |
| knn_ms | 300 | 14.0 | 13.2 | 28.1 | 43.6 | 53.5 |
| fuse_ms | 300 | 0.1 | 0.1 | 0.2 | 0.3 | 0.7 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 93.4 | 80.7 | 187.4 | 222.6 | 268.8 |
