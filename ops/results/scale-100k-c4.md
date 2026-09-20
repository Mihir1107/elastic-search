# Search latency benchmark

Run at 2026-09-20T19:43:28+00:00.

| setting | value |
|---|---|
| index | `emails-v2` |
| documents | 52219 |
| concurrency | 4 |
| iterations | 4 |
| rerank | False |
| requests | 200 (0 failed) |

## Client wall time (the number the gate is about)

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| wall | 200 | 83.5 | 74.8 | 157.8 | 173.3 | 184.6 |

p95 = 157.8 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 200 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 |
| embed_ms | 200 | 30.4 | 32.7 | 52.8 | 55.8 | 57.8 |
| bm25_ms | 200 | 39.7 | 22.1 | 106.5 | 118.0 | 126.8 |
| knn_ms | 200 | 11.0 | 9.9 | 21.5 | 35.1 | 40.6 |
| fuse_ms | 200 | 0.1 | 0.1 | 0.2 | 0.4 | 0.6 |
| rerank_ms | 200 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 200 | 81.3 | 72.4 | 155.2 | 171.3 | 182.9 |
