# Phase 6 — gate evidence

Corpus: **`emails-v2`, 52,219 unique documents** from 100,000 parsed messages across 31
mailboxes (307.4 MB primaries / 614.8 MB with the replica). Cluster: 3 nodes, Basic licence,
3 primaries + 1 replica. Reranking off, per D25.

## Gate 1 — p95 search latency under 300 ms, excluding reranking

**Met.** Three runs of 300 requests at concurrency 4 over the 50 evaluation
queries, measured against a production-mode server with exactly one listener on
the port (verified with `lsof`):

| run | p50 | p95 | p99 |
|---|---:|---:|---:|
| gate-final-r1 | 115.5 ms | 207.8 ms | 264.8 ms |
| gate-final-r2 |  96.1 ms | 189.3 ms | 228.6 ms |
| gate-final-r3 | 100.6 ms | 194.9 ms | 216.3 ms |

**Worst observed p95 is 207.8 ms**, roughly 30% inside the target, and p99 is
under 300 ms in every run.

These numbers are *after* the pagination fix (D32), which is why they differ
from the ones taken earlier in the phase. That fix made the fusion window a
constant — correct, but it put highlighting on the critical path for 120
documents instead of 20 and pushed p95 to 907 ms. Moving highlighting to a
second query over only the returned page brought it back:

| configuration | p95 @ c=4 | pagination |
|---|---:|---|
| variable window, highlight everything | 157.8 ms | **repeats results** |
| constant window 200, highlight everything | 907.3 ms | correct |
| constant window 120, highlight the page only | **~200 ms** | correct |

Scaling by concurrency, measured before the fix but still the shape of it:
latency is governed by concurrency, not corpus size. The same benchmark on the
7,355-document index gave p95 154.7 ms against 157.8 ms on 52,219 documents — a
7x larger corpus for a 2% difference (F16).

## Gate 2 — a chaos run with zero failed requests

**Met.** `ops/results/chaos-final.md`. Killed `es03` — chosen automatically as
the node holding the most primaries — with `docker kill` under live load.

- **2,802 requests, 0 failed (100.00%).**
- Health: green -> **yellow at +0.8 s** -> green **27.5 s after restart**.
- Replica promotion: `emails-v2/2` (plus `emails-v1/1` and `emails-v1/2`) had
  their primaries move onto nodes that were serving replicas before the kill.
- p95 by phase: **197.8 ms before, 203.1 ms during, 364.4 ms after**. The
  outage itself is nearly free; shard recovery is what costs latency (F17).

This only works because `ES_HOST` lists all three published nodes. With one
host configured the client has nowhere to retry, and killing that node fails
every request regardless of cluster health (D28).

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
| vector | 0.6415 | 0.7474 | 0.5022 |
| hybrid | 0.9079 | 0.9569 | 0.7910 |
| hybrid+rerank | 0.8982 | 0.9613 | 0.7910 |

Hybrid improved from 0.8992 to 0.9079 as a side effect of D32: a constant,
wider fusion window fuses a better candidate set. BM25 now leads hybrid by
0.0008 on this query set. See F15 before drawing a conclusion from that:
38 of the 50 queries are graded by phrase/sender/date rules, which is BM25's home ground, and
the 12 conceptual queries — the ones that would test the vector leg and reranking — are still
unlabelled.

## Not claimed

- This is **100,000 of 517,401 messages**. Spec criteria #1 and #8 say the full corpus; this
  does not meet them as written (D27).
- `recall@50` is comparative only; the pool is self-built (D22).
