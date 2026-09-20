# Decisions log

Newest first. Each entry: decision, alternatives considered, reason.

## Research findings (2026-09-20)
- **Elasticsearch 9.5.3** is the latest stable; Python client **9.5.1** (async supported,
  Python 3.10–3.14). Pins chosen accordingly.
- **Enron corpus** download URL `https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz`
  verified live via HTTP HEAD: **443,254,787 bytes**, `Last-Modified 2015-05-07`, extracts to
  ~1.4 GB maildir. Not committed (gitignored).

## D1 — Manual RRF in Python (k=60), not the native RRF retriever
- **Alternatives:** native `rrf` retriever; native `linear` retriever.
- **Reason:** RRF licensing on Basic is genuinely ambiguous — Elastic's subscriptions page
  lists RRF under the free tier, but multiple community reports *and this project's prototype*
  hit `403 current license is non-compliant` on Basic. The hard rule is "nothing may silently
  depend on a paid feature," so we fuse in Python (zero licensing exposure, per-leg weighting,
  trivially unit-testable). Phase 2 adds a startup probe that empirically fires a native `rrf`
  retriever against the pinned cluster and logs whether it 403s, so we *know* the truth for 9.5.3.

## D2 — Chunk vectors as `nested dense_vector` inside the emails index
- **Alternatives:** a separate `chunks` index joined at query time.
- **Reason:** one canonical doc per email keeps dedupe/threading/faceting/atomic updates simple;
  kNN over nested vectors with `inner_hits` collapses to the parent email and yields the best
  chunk as the semantic snippet. kNN-on-nested is a Basic feature.

## D3 — BGE query-instruction asymmetry
- Store passage vectors with no prefix; prepend the BGE query instruction only at search time
  (`bge_query_prefix` in config). Measurable retrieval gain; both model + prefix are swappable.

## D4 — Shard count = 3 primary + 1 replica, chosen for topology not data size
- The corpus fits comfortably in a single shard by volume. 3 primaries + 1 replica = 6 shards
  placeable 2-per-node across 3 nodes with primary/replica never co-located, so any single-node
  loss keeps a full copy and replicas promote (green→yellow→green, zero failed requests) — the
  HA demo (Phase 6). The dev subset keeps the same mapping for prod parity (intentionally over-sharded).

## D5 — Security ON in every compose profile
- TLS + basic auth in both the 3-node and single-node profiles, modeled on Elastic's official
  multi-node compose example, so client config is identical regardless of topology.

## D6 — uv workspace with one shared venv
- Root `pyproject.toml` is a virtual workspace; `api` and `ingest` are members sharing one `.venv`
  so torch (via sentence-transformers) installs once — important given tight disk on the dev laptop.

## D7 — Ingest CLI uses typer
- Typed subcommands, ergonomic, pairs with the FastAPI ecosystem. argparse was the fallback.

## Environment constraints noted (dev laptop: MacBook Air M3, 16 GB)
- **Disk ~14 GB free (97% used):** fine for Phase 0/1; a real risk for the full-corpus Phase 6.
  `make preflight` warns under 8 GB free; we will measure the dev-subset index size to extrapolate.
- **Docker Desktop must be running** for `make up`; give it ≥ 8 GB memory for the 3-node cluster.

---

# Phase 1 (Ingestion)

## D8 — Dev subset = whole mailboxes in hash order, truncated to exactly N
- **Alternatives:** random message-level sampling; first N mailboxes alphabetically.
- **Reason:** message-level random sampling destroys the two structures stages 4 and 5 exist
  to handle — the same email appearing in several mailboxes (dedupe) and reply chains
  (threading). Taking *whole* mailboxes preserves both. Ordering mailboxes by `sha1(name)`
  avoids the alphabetical bias of "first N", and truncating the last mailbox makes the count
  exactly `dev_subset_size`. Fully deterministic, so `make ingest-dev` is reproducible.

## D9 — Chunk on the embedding model's own tokenizer; embed subject + body
- ~200 tokens with 40 overlap, capped at 8 chunks/doc. `bge-small-en-v1.5` truncates around
  512 tokens, so embedding a whole body silently discards most of a long email (flaw #10).
  The subject is prepended to the chunked text because it carries much of an email's topic.

## D10 — Canonical `_id` = SHA-1 over (from, recipients, date, subject, body)
- Content-addressed ids are what make the pipeline idempotent: re-running any stage upserts the
  same documents instead of duplicating them, and cross-mailbox copies collapse naturally.

## D11 — Conservative quoted-reply detection
- Markers: `-----Original Message-----`, `---- Forwarded by`, a long underscore rule,
  `On ... wrote:`, and the start of a `>`-quoted run. A bare `From:` line is deliberately NOT a
  marker: it appears inside legitimate bodies and using it truncated real content.

## D12 — dedupe holds one entry per unique message in memory
- **Alternative:** disk-backed external sort.
- **Reason:** comfortable for the 10k dev subset and workable for the full corpus on this
  machine. Flagged as the first thing to change if full-corpus ingest hits memory pressure.
  Related: `embedded.jsonl` stores vectors as 6-dp floats; a binary sidecar would be the
  full-corpus upgrade if that file gets unwieldy.

---

# Phase 1 findings from the real corpus (10k dev subset, 2026-09-20)

## F1 — The CMU CALO release has NO In-Reply-To or References headers
Verified independently against the raw files: 0 of 2,000 sampled raw messages contain either
header, while all 10,000 have a `Message-ID`. So `thread` links **nothing** by the reply graph on
this corpus (`linked_by_headers: 0`) and the normalised-subject fallback does all the work
(1,549 links, 5,806 threads, 737 multi-message). The header path is not dead code — the
synthetic end-to-end test supplies those headers and exercises it — the corpus simply lacks them.
Worth knowing before anyone "fixes" a threading bug that isn't there.

## F2 — ~26% of messages are cross-mailbox duplicates
10,000 parsed messages collapse to 7,355 unique documents. This is exactly the duplication the
kickoff calls out, and it is why the canonical content-hash `_id` matters.

## F3 — Lotus Notes / X.400 distinguished names appear in recipient headers
e.g. `/o=enron/ou=na/cn=recipients/cn=notesaddr/cn=<id>@enron.com`. `email.utils.getaddresses`
cannot parse them and dropped those recipients silently. `parse` now recovers any address-shaped
token the strict parse misses. Found by spot-checking against raw files, not by a unit test —
which is the argument for keeping that check independent of the parser.

## F4 — The largest "thread" (343 messages) is an automated alert stream
All 343 share the subject `Schedule Crawler: HourAhead Failure` (Dec 2001 - Feb 2002); the next
largest threads are 21/16/13. The subject fallback chains them transitively through the 30-day
window. Defensible (they are the same recurring alert) but a Phase 4 tuning candidate: consider
capping thread size or special-casing machine senders.

## F5 — 351 messages have no usable recipient address
346 genuinely have no `To:` header at all (calendar entries, notes); 5 have a `To:` line that is
prose rather than an address (`To: All Enron Employees:`). Counted, not dropped.
