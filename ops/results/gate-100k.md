# Search latency benchmark

Run at 2026-09-20T21:03:36+00:00.

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
| wall | 300 | 138.4 | 119.5 | 273.6 | 330.2 | 424.3 |

p95 = 273.6 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.1 | 0.3 |
| embed_ms | 300 | 32.9 | 34.2 | 57.4 | 66.1 | 76.8 |
| bm25_ms | 300 | 73.1 | 54.8 | 184.0 | 230.1 | 314.6 |
| knn_ms | 300 | 29.4 | 20.8 | 90.6 | 118.7 | 154.6 |
| fuse_ms | 300 | 0.1 | 0.1 | 0.3 | 0.4 | 0.9 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 135.7 | 116.0 | 270.6 | 328.1 | 421.9 |
