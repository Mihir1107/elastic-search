# Search latency benchmark

Run at 2026-09-20T21:51:49+00:00.

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
| wall | 300 | 105.0 | 96.1 | 189.3 | 228.6 | 268.6 |

p95 = 189.3 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 |
| embed_ms | 300 | 34.6 | 36.7 | 56.1 | 65.4 | 115.8 |
| bm25_ms | 300 | 17.5 | 15.1 | 35.3 | 41.5 | 47.6 |
| knn_ms | 300 | 17.8 | 16.4 | 31.7 | 51.4 | 92.7 |
| fuse_ms | 300 | 0.2 | 0.2 | 0.6 | 0.7 | 2.0 |
| highlight_ms | 300 | 32.1 | 15.2 | 100.2 | 127.7 | 200.6 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 102.4 | 93.6 | 185.7 | 225.5 | 265.2 |
