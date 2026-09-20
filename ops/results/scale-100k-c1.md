# Search latency benchmark

Run at 2026-09-20T19:43:23+00:00.

| setting | value |
|---|---|
| index | `emails-v2` |
| documents | 52219 |
| concurrency | 1 |
| iterations | 4 |
| rerank | False |
| requests | 200 (0 failed) |

## Client wall time (the number the gate is about)

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| wall | 200 | 63.7 | 50.9 | 133.5 | 178.1 | 215.3 |

p95 = 133.5 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 200 | 0.0 | 0.0 | 0.0 | 0.1 | 0.1 |
| embed_ms | 200 | 18.5 | 19.8 | 27.4 | 29.3 | 31.6 |
| bm25_ms | 200 | 33.3 | 17.3 | 91.8 | 134.8 | 178.8 |
| knn_ms | 200 | 8.9 | 7.1 | 18.2 | 28.6 | 42.7 |
| fuse_ms | 200 | 0.1 | 0.1 | 0.3 | 0.3 | 0.3 |
| rerank_ms | 200 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 200 | 61.0 | 48.6 | 131.1 | 176.2 | 213.4 |
