# Search latency benchmark

Run at 2026-09-20T21:04:05+00:00.

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
| wall | 300 | 112.2 | 93.3 | 218.9 | 566.8 | 572.3 |

p95 = 218.9 ms against a 300 ms target: **MET**

## Server stage breakdown

Self-reported by the API, so these exclude transport and serialisation;
the gap between `total_ms` and client wall time is exactly that overhead.

| stage | n | mean | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| parse_ms | 300 | 0.0 | 0.0 | 0.0 | 0.1 | 0.3 |
| embed_ms | 300 | 34.0 | 33.6 | 58.5 | 65.8 | 533.2 |
| bm25_ms | 300 | 58.0 | 32.5 | 155.4 | 213.6 | 510.0 |
| knn_ms | 300 | 17.4 | 13.0 | 35.6 | 51.6 | 508.3 |
| fuse_ms | 300 | 0.1 | 0.1 | 0.2 | 0.4 | 0.4 |
| rerank_ms | 300 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| total_ms | 300 | 109.7 | 90.9 | 216.8 | 565.1 | 570.9 |
