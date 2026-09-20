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

---

# Phase 5 (Frontend)

## D13 — `web/` is Next.js 15 App Router + React 19 + Tailwind v4, pinned exactly
- **Alternatives:** Vite SPA (leaner, no server layer); Streamlit (explicitly ruled out).
- **Reason:** matches the architecture committed in the kickoff (section 3) and keeps a
  server-side seam for the API host. Versions are pinned with exact numbers, matching the
  Python side's `==` convention.

## D14 — The browser never talks to FastAPI directly; everything goes via `/api/proxy/*`
- **Alternatives:** call the API straight from the client with a `NEXT_PUBLIC_API_URL`.
- **Reason:** same reason `config.py` exists — no host or credential belongs in a client
  bundle. It also gives one place to add auth headers when accounts arrive, without
  touching any component. See `web/app/api/proxy/[...path]/route.ts`.

## D15 — A fixture corpus backs the UI until the search API is gated
- The frontend was built while Phase 2 was still in progress, so `web/lib/mock/` implements
  the *shape* of the pipeline (BM25 leg, vector leg, manual RRF at k=60, highlight, facets,
  per-stage timing) over ~36 synthetic emails. `NEXT_PUBLIC_USE_MOCK=false` switches to the
  real API. The fixtures are **not** real Enron mail and are not evaluation data — they
  exist so the interface can be designed and reviewed against realistic text shapes.

## D16 — `web/lib/adapt.ts` absorbs the API/UI contract mismatch
- The API and the UI were written in parallel and named things differently
  (`understood`/`timings`/`snippets`/`matched_by` vs `parsed`/`timing`/`highlight`/`signals`,
  and `folder` is a list server-side but singular in a result row). Rather than spread that
  through every component, one adapter maps the wire format to the view models.
- **Open:** the mapping is written against `api/app/models.py` as of Phase 2 development and
  has **not been exercised against a live API yet**. Two fields are approximations that need
  confirming at the Phase 5 gate: the API reports *which* legs matched (`matched_by`) but not
  the rank within each leg, so the retrieval signal bars show presence rather than depth; and
  `highlight_ms` / `facets_ms` / rerank timing are not broken out, so the timing panel omits
  them instead of inventing numbers.

## D17 — Two marker inks carry "why did this match"
- Yellow marks terms the keyword leg matched; blue marks the chunk the vector leg returned.
  Success criterion #4 is "highlighted snippets showing WHY a result matched", and with a
  hybrid pipeline the honest answer has two cases. The legend is taught on the landing screen
  before any result is shown.

## D18 — The query parser is mirrored (not moved) into the client
- `web/lib/query.ts` re-implements enough of the parser to paint chips inside the search box
  as the user types. `api/app/search/parser.py` stays authoritative and re-parses every query;
  the client copy is presentational only. Divergence shows up as a wrong chip colour, never as
  wrong results — but the two should be kept in step.

---

# Phase 2 (Search API)

## D13 — Fuzziness expressed as `AUTO:5,8`, not hand-rolled per-term clauses
- The requirement is "AUTO on free-text terms of length 5 or more only". Elasticsearch's
  `AUTO:[low],[high]` already means exactly that: 0 edits below `low`, 1 edit up to `high`,
  2 above. So one `multi_match` carries the rule instead of splitting the query into per-term
  clauses and reassembling the scoring.
  Ref: elastic.co/docs/reference/elasticsearch/rest-apis/common-options#fuzziness

## D14 — Hybrid pagination is a windowed opaque page token, not raw `search_after`
- **Alternatives:** true `search_after`; native RRF (paid, see D1).
- **Reason:** fusion happens in the API, so no single ES cursor describes the fused order.
  Each leg is fetched to `fusion_window` (200), fused, then sliced by an opaque token carrying
  the offset. This fixes the prototype's hardcoded `size=20` with no pagination (flaw #3) while
  being honest about its limit: past the window the API stops issuing a `next_page_token` and
  says so in `warnings`. `search_after` remains available for the non-fused paths if deep
  pagination is ever needed.

## D15 — `/suggest` avoids `search_as_you_type`
- **Alternative:** add `search_as_you_type` subfields and reindex to `emails-v2`.
- **Reason:** that is a mapping change, and a second index alongside `emails-v1` roughly doubles
  index size — not affordable on this machine right now (the disk filled during Phase 2 and took
  Docker down). A sanitised terms aggregation (people) plus `match_phrase_prefix` (subjects) gives
  callers the same behaviour with no reindex. The upgrade is a mapping bump plus one reindex
  behind the alias whenever disk allows.

## D16 — `total` is the BM25 leg's exact hit count
- For a hybrid query "how many emails match" is ill-defined. The BM25 leg runs the user's filters
  and keywords with `track_total_hits: true`, so its total is the meaningful, explainable number.
  For a filter-only query the leg is `match_all` + filters, which is exactly the filtered count.

## D17 — `/health` reports, never raises
- It answers even when `app.state` was never populated or the cluster is unreachable, degrading to
  `status: "degraded"` with a `detail`. A health endpoint that 500s is useless to the thing
  monitoring it.

## D19 — Phase 5 redesign: warm ivory, a morphing search bar, three columns
- **Brief:** the visual direction was set by two reference designs supplied on 2026-09-20.
  Where they conflicted with earlier choices (D17's cool "document scan" palette), the
  reference wins: the surface is now warm ivory paper with near-black controls.
- The entry screen and the results view share one search field. It is a single element with
  `layoutId="search-pill"` inside a `LayoutGroup`, so committing a query makes it *travel*
  from the hero into the header rather than being swapped for a different bar.
- **The view swap deliberately does not use `AnimatePresence`.** An exiting workspace never
  finished leaving while its result rows (`layout="position"`), the reading pane's exit
  spring and the shared-layout pill were all still animating, which left two views on screen
  at once. Swapping synchronously is also what shared-layout animation actually needs — both
  pills must exist in the same commit to interpolate. The hero's blur-out is sequenced ahead
  of the swap with an explicit `HERO_EXIT_MS` timer instead.

## D20 — Topic tags are fixture-only, and the UI falls back to folders
- Result tags and the "Key topics" panel read `EmailHit.topics`. The fixture corpus derives
  these from its `concepts`; the live API has no topic aggregation, so `adapt.ts` returns an
  empty list and every surface falls back to `folder` (the tab is even relabelled "Folders").
  Adding a topic field later is a mapping plus an aggregation — no frontend change.

## D21 — Saved and History are real but per-browser; Collections is not built
- The reference sidebar has four destinations. Saved (starred emails) and History (recent
  searches) are implemented in `localStorage` — genuinely useful and honest about being
  per-browser, since user accounts are an explicit MVP non-goal. Collections needs sharing,
  so it renders an empty state that says so rather than pretending.

## D22 — Two `text-[...]` utilities on one element are not reliable
- `text-[0.875rem]` plus `text-[var(--color-surface)]` on the same element silently lost the
  colour (Tailwind cannot always tell a length from a colour inside `var()`). The active tab
  sets its colour with an inline style instead. Worth remembering before debugging an
  "invisible" label again.

## D18 — Pagination pins the shard copy and breaks ties explicitly
- **Symptom:** page 2 of a search occasionally repeated results from page 1.
- **Cause:** every page re-runs the search. With `number_of_replicas: 1` on three nodes the
  coordinating node may route consecutive requests to different shard copies. Copies hold the
  same documents but in different segment layouts, so equal-scoring hits come back in a
  different order and an offset into the fused window lands somewhere else.
- **Fix:** a `preference` derived from the query string (so every page of one search reads the
  same copies) plus an explicit secondary sort on the unique `message_id` (so equal scores still
  have exactly one total order). Both legs use the same preference.
- Regression cover walks three pages three times over and asserts identical repeated queries
  return identical orders, so the instability cannot come back as an occasional flake.

---

# Phase 2 finding

## F6 — The native RRF retriever is confirmed NOT available on Basic (ES 9.5.3)
The startup probe fires a real `rrf` retriever at the cluster and records the result; `/health`
reports `native_rrf_available: false`. That settles, by observation on the pinned version, the
conflict noted in D1 between Elastic's subscription page (which lists RRF under Basic) and the
community reports of `403 current license is non-compliant`. Manual RRF was the right call and
remains the only fusion path.

---

# Phase 3 (Evaluation)

## D19 — Judge by objective rule where relevance is derivable, by hand where it is not
- **Alternatives:** label all 50 queries by hand; LLM-label everything.
- **Reason:** for a known phrase, a named sender or a date window, relevance is a property of
  the document, not an opinion. Declaring that rule next to the query makes 38 of 50 queries
  reproducibly judged with no human in the loop and no LLM guesswork. The 12 conceptual queries
  have no such rule and genuinely need judgment, so they are left for a human. LLM pre-labelling
  exists behind `--prelabel` as a *suggestion* in the prompt, off by default because it spends
  credits and because a suggestion anchors the reviewer.

## D20 — Unjudged queries are excluded from the means, never scored zero
- Scoring an unlabelled query as 0 would silently punish every method for a gap in the labelling
  and make the baseline drift as labels are added. `evaluate_run` reports the number of queries
  each mean covers, and the report renders an unjudged category as `--` rather than `0.0000`.

## D21 — The harness runs queries through the real `run_search`
- A `method` parameter selects which legs contribute ("bm25", "vector", "hybrid"). The evaluation
  therefore measures the same parsing, filtering and fusion the HTTP API uses, instead of a
  parallel implementation that would quietly drift from production.

## D22 — Recall@50 is comparative only, because the pool is self-built
- Judgments come from the union of each method's top 20, so every relevant document is one these
  systems already found, and hybrid (which fuses both legs) covers most of that union — hence
  recall near 1.0. It is a fair comparison *between* methods and meaningless as an absolute. The
  report says so in its own Caveats section rather than leaving the number to be misread.
