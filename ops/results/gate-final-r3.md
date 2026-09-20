# Search latency benchmark

Run at 2026-09-20T21:51:57+00:00.

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
| wall | 300 | 106.8 | 100.6 | 194.9 | 216.3 | 285.5 |

p95 = 194.9 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 |
| embed_ms | 300 | 35.7 | 38.4 | 56.6 | 66.4 | 121.5 |
| bm25_ms | 300 | 18.1 | 15.8 | 34.4 | 45.4 | 111.6 |
| knn_ms | 300 | 17.9 | 17.1 | 31.9 | 55.5 | 85.8 |
| fuse_ms | 300 | 0.3 | 0.2 | 0.7 | 1.2 | 2.8 |
| highlight_ms | 300 | 32.2 | 16.6 | 91.8 | 127.7 | 161.9 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 104.3 | 96.8 | 191.2 | 212.9 | 282.9 |
