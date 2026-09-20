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
spec calls out, and it is why the canonical content-hash `_id` matters.

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
- **Reason:** matches the architecture committed in the spec (section 3) and keeps a
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

## D16 — `total` is the BM25 leg's exact hit count, floored by what was returned
- For a hybrid query "how many emails match" is ill-defined. The BM25 leg runs the user's filters
  and keywords with `track_total_hits: true`, so its total is the meaningful, explainable number.
  For a filter-only query the leg is `match_all` + filters, which is exactly the filtered count.
- Amended in Phase 5: that count describes the BM25 leg alone, so a query whose keywords match
  nothing while the vector leg finds plenty reported `total: 0` above a full page of results.
  `total` is now floored at the number of fused hits actually returned, and is 0 only when the
  BM25 leg did not run at all. Caught by an integration test, not by review.

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

---

# Phase 4 (Rerank + tuning)

Every change below had to earn its place with a number, and two of them did not.

## D23 — Reranking is gated to free-text queries
- Ungated, the cross-encoder cost **-0.063 NDCG@10** (0.8565 -> 0.7932), wrecking person-topic
  (-0.133) and exact-lookup (-0.071) while helping only typo'd queries (+0.014).
- The pattern is principled, not noise: when the user supplies an explicit precision signal --
  a quoted phrase, a `from:`/`to:`/date operator -- a semantic reranker should not be allowed to
  overrule it. `rerank_free_text_only` skips reranking for those queries, and with that gate the
  harm to every explicit-signal category disappears.

## D24 — BM25 subject boost lowered from ^3 to ^1, contradicting the spec
- The spec prescribes `subject^3`. Measured on the judged set the effect is monotone and the
  prescription is simply too aggressive: `^5` -0.020, `^3` baseline, `^2` +0.017, `^1` +0.021
  NDCG@10 (and `^1` is +0.060 MRR). `subject^1` dominates on both metrics, so it wins.
- **Caveat, stated plainly:** the grading rules treat a match in the subject and a match in the
  body as equally relevant, so they cannot reward subject boosting even where a human would.
  This is worth re-validating once the conceptual queries are labelled. Boosts are config
  (`bm25_fields`), so re-tuning is `make eval` plus a settings change, not a code change.
- Boosting or removing `from.text`/`to.text` changed nothing (+0.0000) on this query set. They
  are kept because they serve name search without a `from:` operator, which this set never tests.

## D25 — Reranking ships off by default, because the numbers say so
- After D24 fixed the boosts, hybrid improved so much that gated reranking became a net loss
  again: **-0.037 NDCG@10** (0.8775 -> 0.8401) and **-0.051 MRR**. Fixing BM25 captured the gain
  reranking had been providing.
- It also costs 94-188ms per query, reported as its own `timings.rerank_ms` so it can never hide
  inside the total.
- So it is implemented, flagged per request (`?rerank=true`) and per config, and **off**. The
  case it exists for -- conceptual queries -- is the one the judged set cannot yet measure, so
  this decision should be revisited when those 12 queries are labelled.

## D26 — `term_vector: with_positions_offsets` was tried and reverted
- Hypothesis: storing offsets would stop the highlighter re-analysing bodies. Measured on a real
  reindex it made highlighting **worse**: +24% at size 20 (348ms -> 432ms) and +31% at size 200.
- Reverted. The rollback was an alias flip back to `emails-v1` with no reindex and no downtime,
  which is exactly what the versioned-index design is for; the failed `emails-v2` was dropped
  only after it was no longer the live index.

## F8 — Highlighting is the search latency bottleneck (a Phase 6 lever)
Per-stage p50 on the dev subset: parse 0.0ms, embed ~30ms, kNN ~24ms, fuse 0.3ms, BM25 ~170ms --
and isolating the BM25 leg shows essentially all of it is highlighting: the same query costs
**84ms without highlighting and 1885ms with it** at size 200, ~46ms vs ~394ms at size 20.
Current p95 is ~570ms against the spec's 300ms target, so this is the thing to attack in
Phase 6. Term vectors are not the answer (D26); the promising directions are highlighting only
the page (which needs a cheaper second pass than the one measured here, since an extra round
trip cost more than it saved) or a smaller `fragment_size`/field set validated by measurement.

---

# Phase 6 (Scale + HA)

## D27 — Corpus scope is 100k messages, not the full 517k, and that is a stated shortfall
- **Spec criteria #1 and #8 say "the full corpus"; this does not meet them.** Recorded as a
  deliberate choice rather than a redefinition.
- **Measured, not estimated:** `emails-v1` holds 7,355 emails in **42.6 MB of primaries /
  85.1 MB with the replica** (19,104 Lucene docs = 7,355 parents + 11,749 nested chunks). So the
  index is *not* the expensive part: the full corpus would be ~4.4 GB with a replica, comfortably
  inside the 29 GiB free. The earlier disk objection to a full ingest was wrong and is withdrawn.
- What still argues against full: **~5–7 hours** of wall time (embedding 7,355 docs takes ~4
  minutes, so 517k is ~3.5 h before the other stages), and **dedupe holds every message in
  memory** (D12) — 517k records against a 7.75 GiB Docker VM on a 16 GB laptop.
- 100k costs ~40 minutes and ~3 GB peak, and `DEV_SUBSET_SIZE` already parameterises it, so it is
  the same code path over a deterministic *superset* of the existing 5 mailboxes.
- **Why this is defensible for the latency gate:** highlighting cost scales with `fusion_window`
  (200 docs fetched per query), not with corpus size. Only the BM25 term lookup and the HNSW walk
  grow with N, the latter ~log N. Corpus size changes how honest the claim is, not what the fix is.

## F9 — The HA design was never exercisable: only es01 had the bootstrap password
The `elastic` user is served by the **reserved** realm, which reads its password per-node from the
`ELASTIC_PASSWORD` environment variable. Compose set it on es01 only (as Elastic's official example
does), so es02 and es03 answered **401** to the same credentials es01 accepted — verified directly
against ports 9201/9202, and in es02's log: `Authentication of [elastic] was terminated by realm
[reserved]`. A client holding all three nodes would have failed two thirds of its requests, and the
chaos gate could not have been met at all. Fixed by passing `ELASTIC_PASSWORD` to every node.

## D28 — `ES_HOST` is a comma-separated list, and the API client holds every node
- **Alternatives:** sniffing (`sniff_on_start`); a load balancer in front of the cluster.
- **Reason:** the client was constructed with `hosts=[settings.es_host]` — one node. Killing that
  node fails every request no matter how healthy the cluster is, so zero-failure HA was
  unreachable by construction. The client now round-robins across all three published ports and
  retries elsewhere when one stops answering. Sniffing was rejected because the nodes advertise
  their container names (`es01:9200`), which do not resolve from the host.

## D29 — The chaos run kills the node holding the most primaries, not a fixed one
- First run killed `es02`, which happened to hold **only replicas**. 0 failed requests, green →
  yellow → green — and **no promotion at all**, because nothing needed promoting. It passed the
  letter of the gate while demonstrating almost none of it.
- `--container auto` now resolves the node with the most started primaries and kills that. On the
  dev subset that is `es01`, which is also the elected master, so the run exercises master
  re-election as well. Promotion is then evidenced by comparing shard tables: a shard counts as
  promoted only when the node now serving its primary was serving a *replica* before the kill —
  comparing shard ids alone reports every shard as promoted, which a unit test caught.

## F10 — Latency is already at the gate on the dev subset
`ops/bench` over the 50 evaluation queries at concurrency 4 on `emails-v1` (7,355 docs):
**wall p50 125.8 ms, p95 301.4 ms, p99 617.0 ms**, with `bm25_ms` p95 = 234.0 ms the dominant
stage. That is the 300 ms target reached with 7,355 documents, before the corpus grows — F8's
highlighting cost, confirmed with the new instrument.

## F11 — A node loss made search *faster*, not slower
During the outage p50 fell from 130.5 ms to 82.7 ms and p95 from 298.2 ms to 176.1 ms. With one
node gone the coordinating node holds more of the shards it needs locally, so the fan-out costs
less network. Worth stating explicitly because "latency improved during the chaos phase" reads
like an instrumentation bug and is not one.

## D30 — Embedding and reranking run off the event loop
- **Symptom:** search latency scaled almost linearly with concurrency while the corpus stayed
  the same size. Dev subset, `ops/bench`, concurrency 1 / 2 / 4 / 8:
  wall p50 **46.6 / 48.2 / 89.0 / 159.6 ms**, and `bm25_ms` p50 **12.9 / 18.9 / 38.9 / 76.3 ms**
  — while `embed_ms` stayed flat at ~15-19 ms throughout.
- **Cause:** `embed_query` is synchronous CPU work and was called inline in an async handler, so
  it blocked the event loop for its whole duration. `bm25_ms` is wall time around
  `await es.search`, so it absorbed the delay of *other* requests' encoding and looked like an
  Elasticsearch cost. It was not: measured directly against ES, the same query at size 20 costs
  **6.6 ms bare, 26.2 ms with highlighting and facets**.
- **Fix:** `asyncio.to_thread` for both the embedder and the cross-encoder. torch releases the
  GIL inside the forward pass, so a worker thread genuinely overlaps with the loop's I/O.
- **Measured A/B** on `emails-v2` (52,219 docs), same process started twice in production mode,
  the only difference being this change:

  | concurrency | | before | after |
  |---|---|---:|---:|
  | 1 | p50 / p95 | 43.1 / 123.3 ms | 48.6 / 131.6 ms |
  | 4 | p50 / p95 | 88.1 / 165.8 ms | **70.8** / **157.6 ms** |
  | 8 | p50 / p95 / p99 | 152.1 / 249.3 / 322.1 ms | **144.0** / 248.9 / **277.8 ms** |
  | 8 | `bm25_ms` p50 | 78.6 ms | **35.2 ms** |

- **It is not free.** At concurrency 1 the change is ~5 ms *worse*: the thread handoff costs
  something and there is no contention to amortise it against. It earns its keep from
  concurrency 4 upward, which is the condition that matters for a served API, and it fixes the
  stage attribution at every level — `bm25_ms` no longer absorbs other requests' encoding.
- What remains is real compute: several concurrent encodes saturate the CPU. That is a capacity
  limit, not a bug.
- **Method note:** the first "after" figures taken for this entry were measured against a stale
  `uvicorn --reload` process left running by an earlier shell, which `pkill -f "uvicorn
  app.main:app"` never matched because its command line reads `uvicorn api.app.main:app`. Reload
  mode did pick up the edit so the comparison happened to hold, but a reload supervisor is not a
  representative thing to benchmark. The table above replaces those numbers and was taken with
  exactly one listener on the port, verified with `lsof`.

## F12 — Highlight tuning is a dead end; the cost is per document, not per fragment
Measured directly against Elasticsearch, same BM25 query, varying one thing at a time:

| variant | size 20 | size 200 |
|---|---:|---:|
| no highlighting (floor) | 6.5 ms | 8.6 ms |
| current (4 fields, fragment_size 160, 2 fragments) | 24.1 ms | 158.8 ms |
| drop the `.exact` fields | 23.5 ms | 162.2 ms |
| `number_of_fragments: 1`, `fragment_size: 100` | 23.7 ms | 165.6 ms |
| `max_analyzed_offset` 100k -> 10k | — | 145.8 ms |

Every knob is within noise; only the **document count** matters (~0.8 ms per document). This
closes the directions the earlier highlighting notes listed as untried and promising — smaller `fragment_size`,
fewer fragments, a reduced field set. None of them earn anything. (`fvh` is separately ruled
out: it *requires* term vectors, which D26 measured and reverted.)

## F13 — `fusion_window` does not describe a normal request, so shrinking it buys nothing
`service.py` computes `window = min(max(offset + page_size, page_size), fusion_window)`. A first
page of 20 therefore fetches **20 per leg, not 200**; the window only grows as someone pages
deeper. Two consequences worth recording:
- Halving `fusion_window` — the lever this phase opened with — would not touch the common case.
- An evaluation sweep over `fusion_window` (200/150/100/75/50) returned **byte-identical
  metrics**, because the harness runs at `size=50` and `min(50, fusion_window)` is 50 for all of
  them. The sweep proved nothing and was discarded rather than reported as "no relevance cost".

## D31 — The Phase 6 corpus is `emails-v2`: 100,000 messages, 52,219 unique documents
Ingested with `DEV_SUBSET_SIZE=100000 INDEX_VERSION=v2`, no code change to the pipeline.
31 mailboxes (a deterministic superset of the 5 in the dev subset), 108,322 files extracted,
100,000 parsed with 5 skips (1 date-missing, 3 from-missing, 1 message-id-missing), 0 failures
at every stage. 87,428 chunk vectors. **307.4 MB primaries / 614.8 MB with the replica.**

Verified before the alias moved: count 52,219 == expected, smoke query returned hits, 10,000/10,000
sampled documents carried vectors. `emails-v1` is still on disk as the rollback.

Extrapolating the measured footprint to the full corpus gives ~2.2 GB primaries / ~4.5 GB with a
replica, which confirms the D27 projection and, again, that disk was never the obstacle to a full
ingest — time and dedupe memory were.

## F14 — Growing the corpus invalidates the judged pool, and the gate cannot tell that apart from a regression
Running `eval.cli check` against `emails-v2` with the `emails-v1` baseline reported
**hybrid NDCG@10 0.8775 -> 0.4908, delta -0.3867** and exited 1. Nothing about the ranking got
worse. The pool is the union of each method's top 20 over the *old* corpus, so the larger index
surfaces documents that were never judged, and an unjudged document scores 0.

This is a property of pooled evaluation, not a bug, but it is a trap: the regression gate's
output is indistinguishable from a genuine relevance collapse. **Re-pool and re-baseline as part
of any corpus change** — `make eval-pool` then `make eval-baseline`. Because judgments are keyed
on content-hash document ids and the rules are objective (D19), that is automatic for the 38
rule-judged queries; 1,242 new pairs were auto-graded and qrels grew 1,135 -> 1,832.

## F15 — At 52k documents BM25 overtakes hybrid on the judged set
| method | dev subset (7,355 docs) | emails-v2 (52,219 docs) |
|---|---:|---:|
| bm25 | 0.8300 | **0.9087** |
| vector | 0.5911 | 0.6369 |
| hybrid | 0.8775 | 0.8992 |
| hybrid+rerank | 0.8401 | 0.8873 |

Hybrid improved, but BM25 improved more and now leads it by 0.0095 NDCG@10. **This is not
evidence that fusion is not worth it**, and should not be acted on as if it were: the 38 judged
queries are graded by phrase / sender / date rules (D19), which is exactly what BM25 is good at,
and a bigger corpus gives those rules more true positives to find. The vector leg's contribution
is measured entirely on its worst terrain, as the evaluation caveats (D22) warned.

The 12 conceptual queries remain unlabelled, and they are the ones that would test the other
side. Until they are labelled, the honest statement is "BM25 leads on a lexically-graded query
set", not "hybrid is not worth it". Note also that reranking's penalty shrank from **-0.037 to
-0.0119** NDCG@10 at this scale, which is the direction D25 predicted it would move.

## F16 — Latency barely moved with a 7x larger corpus
`emails-v1` (7,355 docs) vs `emails-v2` (52,219 docs), concurrency 4: wall p95 **154.7 ms ->
157.8 ms**. This is the empirical confirmation of the argument in D27: per-query cost is
dominated by the number of documents fetched and highlighted (a page), not by how many documents
exist. It is also why the 100k corpus is a sound basis for the latency claim even though it is
not the full archive.

## F17 — Recovery, not the outage, is the latency cost
Chaos on `emails-v2`, killing `es03` (the node holding the most primaries): p95 **156.2 ms
before, 172.9 ms during the outage, 337.4 ms after the restart**. The expensive phase is shard
recovery competing for I/O, not the degraded cluster. Steady-state p95 is unaffected, and no
request failed in any phase — but "after" is the window where a naive benchmark would record a
breach of the 300 ms target.

## D32 — The fusion window is constant per query, and the page is highlighted separately
- **Bug:** page two of a search repeated results from page one. Found by driving the
  real UI, which pages at size 20; React reported duplicate keys carrying real document ids.
- **Cause:** `window = min(max(offset + page_size, page_size), fusion_window)` grew the
  candidate set with the page. RRF scores a document against whatever it was fused with, so
  `fused[20:40]` taken from a 40-document window is not a continuation of `fused[0:20]` taken
  from a 20-document window — the whole list re-ranks. The existing regression test walked three
  pages at size **5** and passed; at the size the UI actually uses, page two repeated **9 of 20**.
- **Fix, part one:** the window is now `fusion_window`, a constant for the query.
- **That alone broke the latency gate.** Every query then fetched and highlighted the full
  window: p95 at concurrency 4 went **157.8 ms -> 907.3 ms** (and 364.9 ms even at a window of 60).
- **Fix, part two:** highlighting moved off the retrieval query. Fusion needs a wide candidate
  set; highlighting needs only the page. The leg is fetched bare and a second, `ids`-filtered
  query highlights just the returned page, reported as its own `highlight_ms`.

  | configuration | p95 @ c=4 | correct pagination |
  |---|---:|---|
  | variable window, highlight all (before) | 157.8 ms | **no** |
  | constant window 200, highlight all | 907.3 ms | yes |
  | constant window 200, highlight the page | 294.9 ms | yes |
  | **constant window 120, highlight the page** | **220.5 ms** | yes |

- **This is the "highlight only the page" idea that was previously tried and reverted** as
  223 ms -> 422 ms. It loses when the wide query still highlights everything and the second query
  is pure overhead; it wins decisively once the wide query stops highlighting at all. The earlier
  result was real, and so is this one — they were measuring different things.
- `fusion_window` is **120**: six pages of 20, and the best p95 of the sizes measured.
- **Relevance improved**: hybrid NDCG@10 **0.8992 -> 0.9079** after re-pooling, because a
  constant, wider window fuses a better candidate set. The bm25/hybrid gap narrows from 0.0095
  to 0.0008.

## F18 — This corpus has no attachments at all, and that is correct
`has_attachment` is false for all 52,219 documents and no document carries an attachment name.
Verified against the raw maildir: **0 of 3,000 sampled messages** contain
`Content-Disposition: attachment`, and only one is multipart. The CALO release stripped
attachments and kept the `X-FileName` header (the Notes database, e.g. `jarnold.nsf`), not the
files. The Attachments facet is therefore always empty and the UI says so. Like the threading
headers in F1, this is the corpus, not a bug — do not "fix" it.

## F19 — The cross-encoder's first call costs ~8.8 seconds
Toggling Rerank in the UI took **8,796 ms** the first time and **569 ms** warm (against 255 ms
with reranking off). The difference is the model loading lazily on first use. Reranking is off by
default (D25), so the API does not pay that at startup; the cost lands on whoever turns it on
first. Left lazy deliberately — an off-by-default feature should not slow every boot — but the
first-use latency is real and the UI shows a pending state through it.

## D33 — Mangled smart punctuation is repaired at ingest, and defensively at display
The CALO release stores a right single quote as a control byte plus an ASCII tail, so "Enron's"
arrives as `Enron\x01,s` and paints as "Enron ,s". Measured at **131 of 20,001 documents**.
`ingest.parse.clean_text` repairs it at the source so the indexed text is right; `lib/format.ts`
repeats the repair for display because the serving index predates the parser fix. A full reindex
for 0.65% of documents was not judged worth ~50 minutes of re-embedding — the display fix makes
it invisible now, and the next ingest fixes it properly.
