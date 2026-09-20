# Search latency benchmark

Run at 2026-09-20T21:04:19+00:00.

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
| wall | 300 | 90.2 | 78.5 | 175.5 | 202.0 | 221.2 |

p95 = 175.5 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.1 | 0.3 |
| embed_ms | 300 | 32.7 | 34.0 | 58.2 | 63.0 | 69.9 |
| bm25_ms | 300 | 42.5 | 23.9 | 120.8 | 135.9 | 154.6 |
| knn_ms | 300 | 12.4 | 10.9 | 26.6 | 44.0 | 57.6 |
| fuse_ms | 300 | 0.1 | 0.1 | 0.2 | 0.3 | 0.6 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 87.9 | 76.5 | 173.1 | 199.9 | 218.6 |
