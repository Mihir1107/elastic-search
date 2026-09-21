/**
 * Translates the FastAPI wire format into the view models the components use.
 *
 * The API (api/app/models.py) and this UI were built in parallel, so their
 * shapes differ: the API says `understood`/`timings`/`snippets`/`matched_by`,
 * the UI wants `parsed`/`timing`/`highlight`/`signals`. Rather than scatter
 * that difference through every component, it is absorbed here — this file is
 * the only thing that needs editing if the API contract moves again.
 *
 * Verify against api/app/models.py before trusting it in production.
 */

import type {
  DateBucket,
  EmailDoc,
  EmailHit,
  Facets,
  Health,
  ParsedQuery,
  SearchResponse,
  Suggestion,
  ThreadResponse,
  Timing,
} from "./types";

/* ---- wire types, mirroring api/app/models.py ---- */

interface WireFacet {
  key: string | number | boolean;
  count: number;
}

interface WireTimings {
  parse_ms: number;
  embed_ms: number;
  bm25_ms: number;
  knn_ms: number;
  fuse_ms: number;
  rerank_ms: number;
  total_ms: number;
}

interface WireUnderstood {
  terms: string[];
  phrases: string[];
  from: string[];
  to: string[];
  cc: string[];
  subject: string[];
  after: string | null;
  before: string | null;
  corrections?: { original: string; suggested: string }[];
}

interface WireHit {
  id: string;
  score: number;
  subject: string;
  from: string;
  from_name: string;
  to: string[];
  cc: string[];
  date: string | null;
  thread_id: string | null;
  mailboxes: string[];
  folder: string[];
  has_attachment: boolean;
  duplicate_count: number;
  snippets: string[];
  /** Which retrieval legs returned this document, e.g. ["bm25", "knn"]. */
  matched_by: string[];
  message_id: string;
  attachment_names: string[];
  /** 1-based position inside each leg; null when that leg did not return it. */
  bm25_rank: number | null;
  vector_rank: number | null;
}

interface WireSearch {
  query: string;
  understood: WireUnderstood;
  total: number;
  size: number;
  hits: WireHit[];
  facets: Record<string, WireFacet[]>;
  timings: WireTimings;
  warnings: string[];
  next_page_token: string | null;
  reranked: boolean;
}

interface WireEmail extends Omit<WireHit, "snippets" | "matched_by" | "score"> {
  message_id: string;
  bcc: string[];
  body: string;
  quoted_text: string;
  attachment_names: string[];
}

interface WireThread {
  thread_id: string;
  total: number;
  messages: WireEmail[];
}

interface WireSuggest {
  prefix: string;
  suggestions: { value: string; kind: string; count: number | null }[];
}

interface WireHealth {
  status: string;
  elasticsearch: string | null;
  cluster_name: string | null;
  number_of_nodes: number | null;
  license_tier: string | null;
  active_index: string[];
  alias: string;
  active_shards: number | null;
  docs: number | null;
}

/* ---- adapters ---- */

/** The API reports a single `folder` list; the UI shows one folder per row. */
function firstFolder(folder: string[]): string {
  return folder[0] ?? "";
}

function adaptTiming(t: WireTimings): Timing {
  return {
    parse_ms: t.parse_ms,
    bm25_ms: t.bm25_ms,
    // `embed_ms` is the query-encoding cost, which belongs to the vector leg.
    vector_ms: t.knn_ms + t.embed_ms,
    fusion_ms: t.fuse_ms,
    // Reranking reports its own cost so it can never hide inside the total;
    // 0 means it did not run for this query.
    rerank_ms: t.rerank_ms > 0 ? t.rerank_ms : null,
    // Highlighting and faceting happen inside the BM25 request, so the API
    // cannot separate them without a second round trip. Left at 0 rather than
    // invented, for a panel people are meant to trust.
    highlight_ms: 0,
    facets_ms: 0,
    total_ms: t.total_ms,
  };
}

export function adaptHit(h: WireHit, reranked = false): EmailHit {
  const legs = h.matched_by ?? [];
  const bm25 = legs.includes("bm25");

  return {
    id: h.id,
    message_id: h.message_id ?? "",
    thread_id: h.thread_id ?? "",
    subject: h.subject,
    from: h.from,
    from_name: h.from_name,
    to: h.to,
    cc: h.cc,
    date: h.date ?? "",
    folder: firstFolder(h.folder),
    mailboxes: h.mailboxes,
    has_attachment: h.has_attachment,
    attachment_names: h.attachment_names ?? [],
    duplicate_count: h.duplicate_count,
    // A knn-only hit has no highlighted terms, so its snippet is the matched
    // chunk and is rendered with the semantic marker instead.
    highlight: bm25 && h.snippets.length ? { body: h.snippets.slice(0, 1) } : {},
    semantic_snippet: !bm25 && h.snippets.length ? stripTags(h.snippets[0]) : null,
    signals: {
      // Real positions inside each leg, straight from the fusion step.
      bm25_rank: h.bm25_rank,
      vector_rank: h.vector_rank,
      rrf: h.score,
      // When reranking ran, `score` IS the cross-encoder score, not an RRF one.
      rerank: reranked ? h.score : null,
    },
    topics: [],
  };
}

function stripTags(s: string): string {
  return s.replace(/<\/?em>/g, "");
}

function bucketsOf(
  facets: Record<string, WireFacet[]>,
  key: string,
): { key: string; doc_count: number }[] {
  return (facets[key] ?? []).map((b) => ({
    key: String(b.key),
    doc_count: b.count,
  }));
}

function adaptFacets(f: Record<string, WireFacet[]>): Facets {
  const attachment = f.has_attachment ?? [];
  const truthy = attachment.find((b) => b.key === true || b.key === "true");
  const falsy = attachment.find((b) => b.key === false || b.key === "false");

  const overTime: DateBucket[] = (f.over_time ?? []).map((b) => {
    const iso = String(b.key);
    return {
      key_as_string: iso.slice(0, 10),
      key: Date.parse(iso),
      doc_count: b.count,
    };
  });

  return {
    senders: bucketsOf(f, "top_senders"),
    recipients: bucketsOf(f, "top_recipients"),
    folders: bucketsOf(f, "folders"),
    // No topic aggregation server-side yet; the UI falls back to folders.
    topics: [],
    date_histogram: overTime,
    attachments: { with: truthy?.count ?? 0, without: falsy?.count ?? 0 },
  };
}

function adaptParsed(u: WireUnderstood, query: string): ParsedQuery {
  return {
    // Chips are drawn from the raw string by the client tokenizer, so the
    // server's token spans are not needed here.
    tokens: [],
    free_text: (u.terms ?? []).join(" "),
    phrases: u.phrases ?? [],
    filters: {
      from: u.from?.length ? u.from : undefined,
      to: u.to?.length ? u.to : undefined,
      cc: u.cc?.length ? u.cc : undefined,
      after: u.after ?? undefined,
      before: u.before ?? undefined,
    },
    corrections: u.corrections ?? [],
    ...(query ? {} : {}),
  };
}

export function adaptSearch(w: WireSearch): SearchResponse {
  return {
    query: w.query,
    parsed: adaptParsed(w.understood, w.query),
    total: w.total,
    total_relation: "eq",
    hits: (w.hits ?? []).map((h) => adaptHit(h, w.reranked)),
    facets: adaptFacets(w.facets ?? {}),
    timing: adaptTiming(w.timings),
    next_page_token: w.next_page_token,
    reranked: w.reranked ?? false,
    warnings: w.warnings ?? [],
  };
}

export function adaptEmail(w: WireEmail): EmailDoc {
  return {
    id: w.id,
    message_id: w.message_id ?? "",
    thread_id: w.thread_id ?? "",
    subject: w.subject,
    from: w.from,
    from_name: w.from_name,
    to: w.to,
    cc: w.cc,
    date: w.date ?? "",
    folder: firstFolder(w.folder),
    mailboxes: w.mailboxes,
    has_attachment: w.has_attachment,
    attachment_names: w.attachment_names ?? [],
    duplicate_count: w.duplicate_count,
    highlight: {},
    semantic_snippet: null,
    signals: { bm25_rank: null, vector_rank: null, rrf: 0, rerank: null },
    topics: [],
    body: w.body ?? "",
    quoted_text: w.quoted_text ?? "",
  };
}

export function adaptThread(w: WireThread): ThreadResponse {
  const messages = (w.messages ?? []).map(adaptEmail);
  return {
    thread_id: w.thread_id,
    // The API does not name the thread; the earliest subject is the closest
    // thing to one, with the reply prefix removed.
    subject: messages[0]?.subject.replace(/^(re|fw|fwd):\s*/i, "") ?? "",
    messages,
  };
}

export function adaptSuggest(w: WireSuggest): Suggestion[] {
  return (w.suggestions ?? []).map((s) => ({
    kind: s.kind === "person" ? "person" : "subject",
    value: s.value,
    label: s.value,
    doc_count: s.count ?? 0,
  }));
}

export function adaptHealth(w: WireHealth): Health {
  const ok = w.status === "ok";
  const colour = w.elasticsearch;
  return {
    status: ok ? "ok" : "degraded",
    cluster: {
      status:
        colour === "green" || colour === "yellow" || colour === "red"
          ? colour
          : "red",
      number_of_nodes: w.number_of_nodes ?? 0,
      active_shards: w.active_shards ?? 0,
    },
    license: w.license_tier ?? "unknown",
    index: w.active_index?.[0] ?? w.alias,
    docs: w.docs ?? 0,
  };
}
