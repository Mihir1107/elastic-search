# Phase 6 — gate evidence

Corpus: **`emails-v2`, 52,219 unique documents** from 100,000 parsed messages across 31
mailboxes (307.4 MB primaries / 614.8 MB with the replica). Cluster: 3 nodes, Basic licence,
3 primaries + 1 replica. Reranking off, per D25.

## Gate 1 — p95 search latency under 300 ms, excluding reranking

**Met.** Four runs of 300 requests at concurrency 4 over the 50 evaluation queries:

| run | p50 | p95 | p99 |
|---|---:|---:|---:|
| gate-100k    | 119.5 ms | 273.6 ms | 330.2 ms |
| gate-100k-r1 |  93.3 ms | 218.9 ms | 566.8 ms |
| gate-100k-r2 |  83.7 ms | 190.3 ms | 225.2 ms |
| gate-100k-r3 |  78.5 ms | 175.5 ms | 202.0 ms |

Every run is under the target; the **worst observed p95 is 273.6 ms**, so the margin on a loaded
laptop is about 10%, not the 45% the best run implies. Quoted honestly: p95 sits in the
175–275 ms band at concurrency 4, and p99 is *not* under 300 ms in every run.

Scaling by concurrency (single clean run, production-mode server, one listener):

| concurrency | p50 | p95 | p99 |
|---|---:|---:|---:|
| 1 | 50.9 ms | 133.5 ms | 178.1 ms |
| 4 | 74.8 ms | 157.8 ms | 173.3 ms |
| 8 | 139.3 ms | 254.6 ms | 303.7 ms |

Latency is governed by concurrency, not corpus size: the same measurement on the 7,355-document
index gave p95 154.7 ms at concurrency 4 against 157.8 ms here, a 7x larger corpus (F16).

## Gate 2 — a chaos run with zero failed requests

**Met.** `ops/results/chaos-100k.md`. Killed `es03` — chosen automatically as the node holding
the most primaries — with `docker kill` under live load.

- **3,654 requests, 0 failed (100.00%).**
- Health: green → **yellow at +1.4 s** → green **27 s after restart**.
- Replica promotion: `emails-v2/2` (plus `emails-v1/1` and `emails-v1/2`) had their primaries
  move onto nodes that were serving replicas before the kill.
- p95 by phase: **156.2 ms before, 172.9 ms during, 337.4 ms after**. The outage is cheap; shard
  recovery is what costs latency (F17).

## Gate 3 — snapshots, restoring into a new index version

**Met.** `make snapshot` → `emails-v2-20260920t195232`, SUCCESS, 3 shards, 0 failed, 3,008 ms.
`make restore SNAP=...` → `emails-v3`, 52,219 documents, green, queryable, and the `emails`
alias still resolving to `emails-v2`. The restored index was dropped afterwards; it was never
aliased and never served.

## Relevance at this scale

Re-pooled and re-baselined for the new corpus (required — see F14):

| method | NDCG@10 | MRR | Recall@50 |
|---|---:|---:|---:|
| bm25 | **0.9087** | 0.9737 | 0.6592 |
| vector | 0.6369 | 0.7474 | 0.4999 |
| hybrid | 0.8992 | 0.9560 | 0.8287 |
| hybrid+rerank | 0.8873 | 0.9613 | 0.8287 |

BM25 leads hybrid by 0.0095 on this query set. See F15 before drawing a conclusion from that:
38 of the 50 queries are graded by phrase/sender/date rules, which is BM25's home ground, and
the 12 conceptual queries — the ones that would test the vector leg and reranking — are still
unlabelled.

## Not claimed

- This is **100,000 of 517,401 messages**. Spec criteria #1 and #8 say the full corpus; this
  does not meet them as written (D27).
- `recall@50` is comparative only; the pool is self-built (D22).
