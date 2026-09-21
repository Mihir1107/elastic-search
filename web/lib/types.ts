/**
 * Wire types for the Ledger search API.
 *
 * These mirror the endpoint contract in docs/SPEC.md section 6. The
 * backend (Phase 2) is not built yet, so `lib/mock/engine.ts` implements the
 * same shapes in the browser. When the real API lands, only `lib/api.ts`
 * changes — every component here is already speaking the final contract.
 */

/** How the query parser classified one span of the raw query string. */
export type TokenKind = "phrase" | "person" | "date" | "text" | "unknown";

export interface QueryToken {
  kind: TokenKind;
  /** Field operator when the token came from one: from / to / cc / subject. */
  field?: "from" | "to" | "cc" | "subject";
  /** The operand, with quotes and the `field:` prefix stripped. */
  value: string;
  /** Exact source text, so the UI can align chips to the input. */
  raw: string;
  start: number;
  end: number;
  /** Set on free-text terms the parser will send with fuzziness AUTO. */
  fuzzy?: boolean;
}

export interface ParsedQuery {
  tokens: QueryToken[];
  /** Free text that feeds the hybrid retrieval path. */
  free_text: string;
  phrases: string[];
  filters: SearchFilters;
}

export interface SearchFilters {
  from?: string[];
  to?: string[];
  cc?: string[];
  folder?: string[];
  /** Inclusive ISO date bounds. */
  after?: string;
  before?: string;
  has_attachment?: boolean;
}

/** Why a hit surfaced: its rank in each retrieval leg, and the fused score. */
export interface HitSignals {
  /** 1-based rank in the BM25 leg, or null if that leg did not return it. */
  bm25_rank: number | null;
  /** 1-based rank in the kNN leg, or null. */
  vector_rank: number | null;
  /** Reciprocal rank fusion score (k=60), see DECISIONS.md D1. */
  rrf: number;
  /** Cross-encoder score when rerank=true, else null. */
  rerank: number | null;
}

export interface EmailHit {
  id: string;
  message_id: string;
  thread_id: string;
  subject: string;
  from: string;
  from_name: string;
  to: string[];
  cc: string[];
  /** UTC ISO-8601. */
  date: string;
  folder: string;
  mailboxes: string[];
  has_attachment: boolean;
  attachment_names: string[];
  duplicate_count: number;
  /** ES highlight fragments, containing <em> tags around matched terms. */
  highlight: { subject?: string[]; body?: string[] };
  /** Best-matching chunk, returned when the hit came from the vector leg. */
  semantic_snippet: string | null;
  signals: HitSignals;
  /**
   * Short topic labels shown as tags on a result. The fixture corpus carries
   * these; the live API has no topic field yet, so it returns an empty list and
   * the UI falls back to the folder. See DECISIONS.md D19.
   */
  topics: string[];
}

/** A full email, as returned by GET /emails/{id}. */
export interface EmailDoc extends EmailHit {
  body: string;
  quoted_text: string;
}

export interface FacetBucket {
  key: string;
  doc_count: number;
  /** Display name when the key is an address. */
  label?: string;
}

export interface DateBucket {
  /** Bucket start, ISO date. */
  key_as_string: string;
  key: number;
  doc_count: number;
}

export interface Facets {
  senders: FacetBucket[];
  recipients: FacetBucket[];
  folders: FacetBucket[];
  /** Empty when the backend does not aggregate topics. */
  topics: FacetBucket[];
  date_histogram: DateBucket[];
  attachments: { with: number; without: number };
}

/** Per-stage latency, so the UI can show where the time went. */
export interface Timing {
  parse_ms: number;
  bm25_ms: number;
  vector_ms: number;
  fusion_ms: number;
  rerank_ms: number | null;
  highlight_ms: number;
  facets_ms: number;
  total_ms: number;
}

export interface SearchResponse {
  query: string;
  parsed: ParsedQuery;
  total: number;
  /** ES reports "gte" once the count exceeds track_total_hits. */
  total_relation: "eq" | "gte";
  hits: EmailHit[];
  facets: Facets;
  timing: Timing;
  next_page_token: string | null;
  reranked: boolean;
  /** Human-readable notes from the API, e.g. why a requested rerank was skipped. */
  warnings: string[];
}

export interface ThreadResponse {
  thread_id: string;
  subject: string;
  messages: EmailDoc[];
}

export interface Suggestion {
  kind: "person" | "subject";
  value: string;
  label: string;
  doc_count: number;
}

export interface Health {
  status: "ok" | "degraded";
  cluster: {
    status: "green" | "yellow" | "red";
    number_of_nodes: number;
    active_shards: number;
  };
  license: string;
  index: string;
  docs: number;
}

export interface SearchParams {
  q: string;
  filters: SearchFilters;
  size?: number;
  page_token?: string | null;
  rerank?: boolean;
}
