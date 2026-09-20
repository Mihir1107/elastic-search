# Handoff — state, traps, and what to do next

Written at the end of the session that built Phases 0–5. Read this **and**
`CLAUDE.md`, `DECISIONS.md` and `CLAUDE_CODE_KICKOFF.md` before touching anything.

---

## 1. Where the project actually is

| Phase | State | Gate evidence |
|---|---|---|
| 0 Foundation | **done** | green 3-node ES 9.5.3 w/ TLS, `make up`, CI, pinned deps |
| 1 Ingestion | **done** | 7,355 docs indexed, 0 failures across 7 stages, 200/200 spot-check |
| 2 Search API | **done** | parser 100% line coverage, hybrid retrieval, facets, pagination |
| 3 Evaluation | **done** | baseline committed, 38/50 queries judged by objective rule |
| 4 Rerank + tuning | **done** | +0.021 NDCG@10 / +0.060 MRR; two changes reverted on measurement |
| 5 Frontend | **done** | `web/` wired to the live API end to end |
| 6 Scale + HA | **NOT STARTED** | this is your job |

`git log --oneline` is the real record. 183 tests pass; `make lint`, `make typecheck`,
`uv run pytest -q` are all green. Keep them that way.

### The live system right now
- Index `emails-v1`, alias `emails`, **7,355 documents** (deduped from 10,000 parsed).
- Corpus subset = 5 mailboxes: `arnold-j forney-j quenet-j storey-g williams-w3`.
  The full archive is **517,401 messages across 150 mailboxes**.
- Baseline (38 judged queries), `eval/results/baseline.json`:
  `hybrid 0.8775 ndcg@10 / 0.9539 mrr` · `bm25 0.8300 / 0.9160` ·
  `vector 0.5911 / 0.7624` · `hybrid+rerank 0.8401 / 0.9031`.

---

## 2. Hard rules — do not break these

1. **Never delete a live index.** `emails-v1` is serving. Write `emails-vN`, verify count +
   smoke query, flip the alias, and only then consider the old one.
2. **Never commit** `data/`, `eval/pools.json`, `.env`, `web/.env.local`, `certs/`,
   `node_modules/`, `.next/`. All are gitignored; one of them (pools.json, 3.5 MB of email
   bodies) was committed by accident and had to be removed.
3. **Basic licence only.** Native RRF is **confirmed unavailable** — see §3.1. Reranking is a
   local cross-encoder, never Elastic's `text_similarity_reranker`.
4. **Every tuning change must be justified by a metric delta** and `uv run python -m eval.cli check`
   must stay green (fails on >2 point hybrid NDCG@10 regression).
5. **Do not rewrite `web/`.** The design, components and copy are the user's. Fix defects and
   wire capability; do not restyle wholesale.
6. **Do not prune the user's Docker images or caches** without asking. Their machine was 99%
   full; they cleared it themselves. Ask, don't assume.

---

## 3. Findings you would otherwise rediscover the hard way

### 3.1 Native RRF is not available on Basic (settled empirically)
The docs conflict: Elastic's subscriptions page lists RRF under Basic; the retriever 403s in
reality. The API probes it at startup and `/health` reports
`native_rrf_available: false` (`AuthorizationException`). **Fusion is manual RRF (k=60) in
`api/app/search/fusion.py`. Do not "simplify" it to the native retriever.**

### 3.2 This corpus has no threading headers
Verified against raw files: **0 of 2,000 sampled messages carry `In-Reply-To` or `References`**,
though all have `Message-ID`. So `thread` links nothing by the reply graph and the
normalised-subject fallback does all the work. `linked_by_headers: 0` in the stats is **correct,
not a bug**. The header path is exercised by the synthetic end-to-end test.

### 3.3 Highlighting is the latency bottleneck (this is Phase 6's real problem)
Same query, size 200: **84 ms without highlighting, 1885 ms with it.** Current p95 ≈ **570 ms**
against the kickoff's **300 ms** target (excluding rerank). Two fixes were tried and **reverted
because they measured worse**:
- `term_vector: with_positions_offsets` on subject/body → highlighting got **24–31% slower**.
- Highlighting only the page via a second filtered query → total went **223 ms → 422 ms** (the
  extra round trip cost more than it saved).
Do not retry either without new evidence. Untried directions: smaller `fragment_size`, fewer
fragments, `fvh` highlighter, or accepting the cost and measuring p95 excluding highlight.

### 3.4 Other things that bit
- **Lotus Notes / X.400 DNs** appear in recipient headers
  (`/o=enron/ou=na/cn=recipients/cn=<id>@enron.com`). `email.utils.getaddresses` cannot parse
  them and silently dropped recipients; `parse.py` now recovers address-shaped tokens.
- **`X-From` is usually not a name** — `api/app/names.py` cleans it for display.
- **Pagination needs both** a query-derived `preference` and a `message_id` tiebreaker. Without
  them, consecutive pages read different shard copies and repeat results. Do not remove either.
- **`total`** is the BM25 leg's count floored by the number of fused hits returned — a
  semantic-only query used to report `total: 0` above a full page of results.
- **ES emits hex HTML entities** (`&#x27;`, not `&#39;`).
- **Tailwind v4**: `text-[var(--color-x)]` can emit *no rule at all* when the element already
  carries another `text-*` utility. Set the colour inline (see `Tabs.tsx`, `Insights.tsx`).

### 3.5 Read the evaluation honestly
- **recall@50 is inflated by pool bias** — judgments come from the union of each method's top 20,
  so hybrid covers most of the pool by construction. Compare methods with it; never quote it as
  an absolute.
- **The judged set skews lexical.** 38 queries are judged by objective rule (phrase / sender /
  date), which is BM25's home turf. **The 12 conceptual queries are still unlabelled**, and those
  are exactly where the vector leg and reranking should win. The vector leg's 0.59 is being
  measured on its worst terrain.

---

## 4. Environment traps (these cost real time last session)

1. **`timeout` is not on PATH.** `until timeout 15 docker info` exits 127 forever and looks like
   "Docker is down". It isn't. Use `curl --max-time`, or the Bash tool's own `timeout` parameter.
2. **Docker Desktop's VM is ~7.65 GiB** while the host has far more. Three ES nodes at a 2 GiB cap
   each is tight. `make up-single` exists for low-RAM work (expect **yellow**, not green — a
   replica cannot assign on one node).
3. **Disk.** The machine was 99% full and Docker crashed mid-session, taking the cluster down
   (everything survived). ~17 GiB free at handoff. **The corpus tarball was deleted after
   extraction** — a full ingest re-downloads 423 MB.
4. **Next.js inlines `NEXT_PUBLIC_*` at build time.** After changing `web/.env.local` you must
   `rm -rf web/.next`, or the UI keeps serving the fixture corpus. It is easy to miss because the
   **mock health response is identical to the real one** (`3 nodes / basic / emails-v1`). Confirm
   with the *results*, not the health pill.
5. **Playwright** holds a Chrome profile lock; a stale automation browser must be killed before a
   new session can attach.
6. `.venv` is a **uv workspace** at the repo root; run everything with `uv run`.

---

## 5. Phase 6 — what to actually do

Kickoff gate: **p95 < 300 ms (excluding reranking) on the full corpus, and a chaos run with 0
failed requests.** Plan it, get approval, then build. Suggested order:

1. **Decide the corpus target with the user first.** A full ingest is ~517k messages. Embedding
   7,355 docs took ~4 minutes, so the full set is **roughly 4–6 hours** on this laptop, plus
   ~1.4 GB extracted and a much larger index with vectors and a replica. **Check free disk and
   agree the scope before starting** — this is the single biggest risk in the phase. A middle
   option (e.g. 100k) may prove the latency and HA points at far lower cost; say so rather than
   silently doing less or blindly doing more.
2. **Latency.** Build `ops/bench/` (locust headless or a simple async client), report
   p50/p95/p99 per stage. Attack §3.3 with measurements, not hypotheses. Every change needs a
   before/after number, and `eval.cli check` must stay green.
3. **Chaos** (`ops/chaos/`): start load, `docker kill` one node, record green→yellow→green,
   replica promotion, and **request success rate (target 0 failures)**, restart, show recovery,
   print p50/p95 before/during/after. The compose file already publishes es01/es02/es03 on
   9200/9201/9202 so a client can hold all three.
4. **Snapshots** (`ops/snapshots/`): the compose file already has a `snapshots` volume and
   `path.repo=/snapshots` on every node. Add `make snapshot` and `make restore` — restore into a
   **new index version**, never over the live one.

### Also outstanding (smaller)
- **Label the 12 conceptual queries**: `make eval-label` (or `--prelabel` for LLM suggestions).
  This is the single highest-value thing for making the numbers honest, and it will likely move
  the vector and rerank verdicts. Re-run `make eval-baseline` afterwards and say what changed.
- Reranking is **off by default** and that is measured, not arbitrary. If labelling conceptual
  queries flips the verdict, change the default *and* record the delta in `DECISIONS.md`.
- `/suggest` uses a terms aggregation + `match_phrase_prefix` instead of `search_as_you_type`
  (D15) purely to avoid a second index while disk was tight. Revisit if disk allows.

---

## 6. How to run it

```bash
make up                 # 3-node cluster (green), exports certs/ca.crt
make health             # cluster + licence + active index
uv run uvicorn app.main:app --app-dir api --port 8000
cd web && npm run dev   # http://localhost:3000

make test               # fast unit tests
uv run pytest -q        # everything, needs the cluster
make eval               # metrics + eval/results/<date>.md
uv run python -m eval.cli check   # regression gate
```

## 7. How to work

Plan each phase, list the files you will touch, **stop at the gate and wait for approval** — the
user has been running it that way throughout and it has worked. Report failures with the output.
When a change does not earn its keep, revert it and say so; three were reverted last session and
that was the right call each time. If a kickoff requirement turns out to be wrong — `subject^3`
was — say so, show the number, and propose the alternative.
