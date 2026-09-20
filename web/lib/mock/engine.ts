/**
 * In-browser stand-in for the Phase 2 search API.
 *
 * It deliberately mirrors the real pipeline's SHAPE (docs/SPEC.md section 5): a BM25
 * leg, a vector leg, manual RRF at k=60, highlighting, and facet aggregation,
 * each timed separately. The maths is toy — the point is that every field the
 * UI renders is a field the real API will return, so swapping in the backend
 * changes no component.
 */

import { parse } from "../query";
import type {
  EmailDoc,
  EmailHit,
  Facets,
  Health,
  SearchFilters,
  SearchParams,
  SearchResponse,
  Suggestion,
  ThreadResponse,
  Timing,
} from "../types";
import { CORPUS, PEOPLE, type MockDoc } from "./corpus";

/** RRF constant, matching DECISIONS.md D1. */
const K = 60;
const PAGE = 12;

/** Maps query words onto the latent topics carried by `MockDoc.concepts`.
 *  This is what lets "hiding losses" retrieve documents that never use either
 *  word — the behaviour the vector leg exists to provide. */
const CONCEPT_LEXICON: Record<string, string[]> = {
  hiding: ["concealment", "spe", "restatement"],
  hide: ["concealment", "spe"],
  hidden: ["concealment", "spe"],
  conceal: ["concealment"],
  losses: ["writedown", "impairment", "restatement"],
  loss: ["writedown", "impairment"],
  writedown: ["writedown", "impairment"],
  impairment: ["impairment", "writedown"],
  fraud: ["concealment", "restatement", "whistleblower"],
  partnership: ["spe", "ljm", "raptor"],
  partnerships: ["spe", "ljm", "raptor"],
  raptor: ["raptor", "spe"],
  hedge: ["hedging", "raptor"],
  hedges: ["hedging", "raptor"],
  hedging: ["hedging"],
  offbalance: ["spe"],
  vehicle: ["spe"],
  vehicles: ["spe"],
  whistleblower: ["whistleblower"],
  warned: ["whistleblower", "risk"],
  warning: ["whistleblower", "risk"],
  concerns: ["whistleblower", "risk"],
  earnings: ["earnings", "disclosure"],
  restate: ["restatement"],
  restatement: ["restatement"],
  trading: ["trading"],
  california: ["california", "trading"],
  power: ["power", "trading"],
  gas: ["gas", "trading"],
  legal: ["legal", "governance"],
  board: ["board", "governance"],
  audit: ["audit", "governance", "controls"],
  merger: ["merger", "diligence"],
  credit: ["credit", "counterparty", "liquidity"],
  risk: ["risk"],
  disclosure: ["disclosure"],
  conflict: ["conflict", "governance"],
};

const STOP = new Set([
  "the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "is", "are",
  "was", "were", "that", "this", "it", "with", "as", "at", "by", "be", "from",
]);

function terms(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9']+/)
    .filter((t) => t.length > 1 && !STOP.has(t));
}

/** Levenshtein distance, capped — stands in for ES fuzziness AUTO. */
function editDistance(a: string, b: string): number {
  if (Math.abs(a.length - b.length) > 2) return 3;
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  const cur = new Array<number>(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    cur[0] = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(
        prev[j] + 1,
        cur[j - 1] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    for (let j = 0; j <= b.length; j++) prev[j] = cur[j];
  }
  return prev[b.length];
}

function matchesFilters(doc: MockDoc, f: SearchFilters): boolean {
  const inAny = (needles: string[] | undefined, haystack: string[]) =>
    !needles?.length ||
    needles.some((n) => haystack.some((h) => h.toLowerCase().includes(n.toLowerCase())));

  if (!inAny(f.from, [doc.from, doc.from_name])) return false;
  if (!inAny(f.to, doc.to)) return false;
  if (!inAny(f.cc, doc.cc)) return false;
  if (f.folder?.length && !f.folder.includes(doc.folder)) return false;
  if (f.after && doc.date < f.after) return false;
  // `before:` is inclusive of the named day.
  if (f.before && doc.date > `${f.before}T23:59:59Z`) return false;
  if (typeof f.has_attachment === "boolean") {
    if (f.has_attachment !== doc.attachment_names.length > 0) return false;
  }
  return true;
}

/** Toy BM25: field-weighted term frequency with fuzzy fallback. */
function bm25Leg(docs: MockDoc[], free: string[], phrases: string[]): Map<string, number> {
  const scores = new Map<string, number>();
  if (!free.length && !phrases.length) return scores;

  for (const doc of docs) {
    const subjectTerms = terms(doc.subject);
    const bodyTerms = terms(`${doc.body} ${doc.quoted_text}`);
    let score = 0;

    for (const q of free) {
      const ql = q.toLowerCase();
      const sHits = subjectTerms.filter((t) => t === ql || t.startsWith(ql)).length;
      const bHits = bodyTerms.filter((t) => t === ql || t.startsWith(ql)).length;
      // subject^3, per the spec's multi_match boost.
      score += sHits * 3 + bHits;

      if (sHits === 0 && bHits === 0 && ql.length >= 5) {
        const fuzzyHit = [...subjectTerms, ...bodyTerms].some(
          (t) => editDistance(t, ql) <= (ql.length > 7 ? 2 : 1),
        );
        if (fuzzyHit) score += 0.6;
      }
    }

    for (const p of phrases) {
      const pl = p.toLowerCase();
      if (doc.subject.toLowerCase().includes(pl)) score += 6;
      if (doc.body.toLowerCase().includes(pl)) score += 3;
    }

    if (score > 0) scores.set(doc.id, score);
  }
  return scores;
}

/** Toy kNN: cosine-ish overlap between query concepts and document concepts. */
function vectorLeg(docs: MockDoc[], free: string[]): Map<string, number> {
  const scores = new Map<string, number>();
  const wanted = new Map<string, number>();
  for (const q of free) {
    for (const c of CONCEPT_LEXICON[q.toLowerCase()] ?? []) {
      wanted.set(c, (wanted.get(c) ?? 0) + 1);
    }
  }
  if (!wanted.size) return scores;

  const norm = Math.sqrt([...wanted.values()].reduce((a, b) => a + b * b, 0));
  for (const doc of docs) {
    let dot = 0;
    for (const c of doc.concepts) dot += wanted.get(c) ?? 0;
    if (dot > 0) {
      scores.set(doc.id, dot / (norm * Math.sqrt(doc.concepts.length)));
    }
  }
  return scores;
}

function ranked(scores: Map<string, number>): Map<string, number> {
  const order = [...scores.entries()].sort((a, b) => b[1] - a[1]);
  return new Map(order.map(([id], i) => [id, i + 1]));
}

/** Wraps matched terms in <em>, which is what ES highlighting returns. */
function highlightFragment(text: string, free: string[], phrases: string[]): string | null {
  // Stopwords are not what the query is about, and marking them makes the
  // snippet unreadable. Phrases keep their stopwords, since the user quoted them.
  const needles = [...phrases, ...free.filter((t) => !STOP.has(t.toLowerCase()))].filter(
    Boolean,
  );
  if (!needles.length) return null;

  const escaped = needles
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  // Word boundaries: an English analyser matches whole tokens, so highlighting
  // must too — otherwise "in" lights up the middle of "asking".
  const re = new RegExp(`\\b(${escaped.join("|")})`, "gi");

  const idx = text.search(re);
  if (idx === -1) return null;

  // Centre a ~220 char window on the first match, snapped to word edges.
  const start = Math.max(0, idx - 70);
  const end = Math.min(text.length, start + 220);
  let frag = text.slice(start, end);
  if (start > 0) frag = `…${frag.replace(/^\S*\s/, "")}`;
  if (end < text.length) frag = `${frag.replace(/\s\S*$/, "")}…`;

  return frag.replace(re, "<em>$1</em>");
}

function toHit(
  doc: MockDoc,
  bm25Rank: number | null,
  vecRank: number | null,
  rrf: number,
  free: string[],
  phrases: string[],
  rerank: number | null,
): EmailHit {
  const subjectFrag = highlightFragment(doc.subject, free, phrases);
  const bodyFrag = highlightFragment(`${doc.body} ${doc.quoted_text}`, free, phrases);

  // A hit the keyword leg never saw has nothing to highlight, so the UI shows
  // the best chunk instead — the spec's rule for semantic-only hits.
  const semantic =
    bm25Rank === null && vecRank !== null
      ? doc.body.split(/\n\n/)[0].slice(0, 240)
      : null;

  return {
    id: doc.id,
    message_id: doc.message_id,
    thread_id: doc.thread_id,
    subject: doc.subject,
    from: doc.from,
    from_name: doc.from_name,
    to: doc.to,
    cc: doc.cc,
    date: doc.date,
    folder: doc.folder,
    mailboxes: doc.mailboxes,
    has_attachment: doc.attachment_names.length > 0,
    attachment_names: doc.attachment_names,
    duplicate_count: doc.duplicate_count,
    highlight: {
      ...(subjectFrag ? { subject: [subjectFrag] } : {}),
      ...(bodyFrag ? { body: [bodyFrag] } : {}),
    },
    semantic_snippet: semantic,
    signals: { bm25_rank: bm25Rank, vector_rank: vecRank, rrf, rerank },
    topics: doc.concepts.slice(0, 3),
  };
}

function buildFacets(docs: MockDoc[]): Facets {
  const count = (xs: string[]) => {
    const m = new Map<string, number>();
    for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1);
    return [...m.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([key, doc_count]) => ({ key, doc_count, label: PEOPLE[key] }));
  };

  const months = new Map<string, number>();
  for (const d of docs) {
    const key = `${d.date.slice(0, 7)}-01`;
    months.set(key, (months.get(key) ?? 0) + 1);
  }

  // Fill gap months so the histogram reads as a continuous timeline.
  const keys = [...months.keys()].sort();
  const series: { key_as_string: string; key: number; doc_count: number }[] = [];
  if (keys.length) {
    const cur = new Date(`${keys[0]}T00:00:00Z`);
    const last = new Date(`${keys[keys.length - 1]}T00:00:00Z`);
    while (cur <= last) {
      const k = cur.toISOString().slice(0, 10);
      series.push({ key_as_string: k, key: cur.getTime(), doc_count: months.get(k) ?? 0 });
      cur.setUTCMonth(cur.getUTCMonth() + 1);
    }
  }

  return {
    senders: count(docs.map((d) => d.from)).slice(0, 12),
    recipients: count(docs.flatMap((d) => d.to)).slice(0, 12),
    folders: count(docs.map((d) => d.folder)).slice(0, 12),
    topics: count(docs.flatMap((d) => d.concepts)).slice(0, 10),
    date_histogram: series,
    attachments: {
      with: docs.filter((d) => d.attachment_names.length > 0).length,
      without: docs.filter((d) => d.attachment_names.length === 0).length,
    },
  };
}

/** Latency that scales with work done, so the timing panel shows real shape. */
function timing(candidates: number, rerank: boolean, vectorUsed: boolean): Timing {
  const jitter = (base: number) => Math.round((base + Math.random() * base * 0.4) * 10) / 10;
  const bm25 = jitter(3 + candidates * 0.04);
  const vector = vectorUsed ? jitter(9 + candidates * 0.06) : 0;
  const fusion = jitter(0.4);
  const highlight = jitter(1.2);
  const facets = jitter(2.5);
  const parse = jitter(0.3);
  const rr = rerank ? jitter(60 + candidates * 1.6) : null;
  const total =
    Math.round((parse + bm25 + vector + fusion + highlight + facets + (rr ?? 0)) * 10) / 10;
  return {
    parse_ms: parse,
    bm25_ms: bm25,
    vector_ms: vector,
    fusion_ms: fusion,
    rerank_ms: rr,
    highlight_ms: highlight,
    facets_ms: facets,
    total_ms: total,
  };
}

export function search(params: SearchParams): SearchResponse {
  const parsed = parse(params.q);
  const filters: SearchFilters = { ...parsed.filters, ...params.filters };
  // The analyser drops stopwords, so the mock retrieval legs must too — else
  // "about the budget" matches anything containing "the".
  const free = (parsed.free_text ? parsed.free_text.split(/\s+/) : [])
    .filter(Boolean)
    .filter((t) => !STOP.has(t.toLowerCase()));
  const { phrases } = parsed;

  const pool = CORPUS.filter((d) => matchesFilters(d, filters));

  const hasQuery = free.length > 0 || phrases.length > 0;
  const bm25 = hasQuery ? bm25Leg(pool, free, phrases) : new Map<string, number>();
  const vec = hasQuery ? vectorLeg(pool, free) : new Map<string, number>();

  const bm25Ranks = ranked(bm25);
  const vecRanks = ranked(vec);

  // Manual reciprocal rank fusion (DECISIONS.md D1).
  const fused = new Map<string, number>();
  for (const [id, r] of bm25Ranks) fused.set(id, (fused.get(id) ?? 0) + 1 / (K + r));
  for (const [id, r] of vecRanks) fused.set(id, (fused.get(id) ?? 0) + 1 / (K + r));

  // With no query text at all, browsing the filtered set newest-first is the
  // useful behaviour rather than an empty screen.
  let ordered: { id: string; rrf: number }[];
  if (!hasQuery) {
    ordered = [...pool]
      .sort((a, b) => b.date.localeCompare(a.date))
      .map((d) => ({ id: d.id, rrf: 0 }));
  } else {
    ordered = [...fused.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([id, rrf]) => ({ id, rrf }));
  }

  const rerank = params.rerank ?? false;
  if (rerank && hasQuery) {
    // The cross-encoder sees only the top 50, per the spec.
    const head = ordered.slice(0, 50);
    const byId = new Map(CORPUS.map((d) => [d.id, d]));
    head.sort((a, b) => {
      const sa = scoreCross(byId.get(a.id)!, free, phrases);
      const sb = scoreCross(byId.get(b.id)!, free, phrases);
      return sb - sa;
    });
    ordered = [...head, ...ordered.slice(50)];
  }

  const offset = params.page_token ? Number(params.page_token) : 0;
  const size = params.size ?? PAGE;
  const page = ordered.slice(offset, offset + size);
  const byId = new Map(CORPUS.map((d) => [d.id, d]));

  const hits = page.map(({ id, rrf }) =>
    toHit(
      byId.get(id)!,
      bm25Ranks.get(id) ?? null,
      vecRanks.get(id) ?? null,
      rrf,
      free,
      phrases,
      rerank ? scoreCross(byId.get(id)!, free, phrases) : null,
    ),
  );

  const matchedDocs = ordered.map(({ id }) => byId.get(id)!);

  return {
    query: params.q,
    parsed,
    total: ordered.length,
    total_relation: "eq",
    hits,
    facets: buildFacets(matchedDocs),
    timing: timing(ordered.length, rerank, vec.size > 0),
    next_page_token: offset + size < ordered.length ? String(offset + size) : null,
    reranked: rerank,
  };
}

/** Stand-in cross-encoder: rewards term proximity in the subject line. */
function scoreCross(doc: MockDoc, free: string[], phrases: string[]): number {
  const hay = `${doc.subject} ${doc.body}`.toLowerCase();
  let s = 0;
  for (const q of [...phrases, ...free]) {
    const i = hay.indexOf(q.toLowerCase());
    if (i >= 0) s += 1 / (1 + i / 120);
  }
  return s;
}

export function getEmail(id: string): EmailDoc | null {
  const doc = CORPUS.find((d) => d.id === id);
  if (!doc) return null;
  return {
    ...toHit(doc, null, null, 0, [], [], null),
    body: doc.body,
    quoted_text: doc.quoted_text,
  };
}

export function getThread(threadId: string): ThreadResponse | null {
  const msgs = CORPUS.filter((d) => d.thread_id === threadId).sort((a, b) =>
    a.date.localeCompare(b.date),
  );
  if (!msgs.length) return null;
  return {
    thread_id: threadId,
    subject: msgs[0].subject.replace(/^(re|fw|fwd):\s*/i, ""),
    messages: msgs.map((d) => ({
      ...toHit(d, null, null, 0, [], [], null),
      body: d.body,
      quoted_text: d.quoted_text,
    })),
  };
}

export function suggest(prefix: string): Suggestion[] {
  const p = prefix.toLowerCase().trim();
  if (p.length < 2) return [];

  const people: Suggestion[] = Object.entries(PEOPLE)
    .filter(([addr, name]) => addr.includes(p) || name.toLowerCase().includes(p))
    .map(([addr, name]) => ({
      kind: "person" as const,
      value: addr,
      label: name,
      doc_count: CORPUS.filter((d) => d.from === addr || d.to.includes(addr)).length,
    }));

  const seen = new Set<string>();
  const subjects: Suggestion[] = [];
  for (const d of CORPUS) {
    const clean = d.subject.replace(/^(re|fw|fwd):\s*/i, "");
    if (clean.toLowerCase().includes(p) && !seen.has(clean)) {
      seen.add(clean);
      subjects.push({ kind: "subject", value: clean, label: clean, doc_count: 1 });
    }
  }

  return [...people.sort((a, b) => b.doc_count - a.doc_count).slice(0, 4), ...subjects.slice(0, 4)];
}

export function health(): Health {
  return {
    status: "ok",
    cluster: { status: "green", number_of_nodes: 3, active_shards: 6 },
    license: "basic",
    index: "emails-v1",
    docs: CORPUS.length,
  };
}
