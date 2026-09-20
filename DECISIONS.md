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
