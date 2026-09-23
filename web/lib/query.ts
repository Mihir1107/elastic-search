/**
 * Client-side query tokenizer.
 *
 * This EXISTS ONLY TO DRAW THE CHIPS inside the search field as the user types.
 * The authoritative parser is `api/app/search/parser.py` (Phase 2); the server
 * re-parses every query and its `parsed` block is what the results reflect.
 * Keeping a light mirror here is what makes the field feel instant — we can
 * show "this is a person, this is a phrase" before any request goes out.
 */

import type { ParsedQuery, QueryToken, SearchFilters, TokenKind } from "./types";

const FIELD_OPS = ["from", "to", "cc", "subject"] as const;
const DATE_OPS = ["before", "after"] as const;

type FieldOp = (typeof FIELD_OPS)[number];

/** Terms shorter than this never get fuzziness — matches parser.py's rule. */
const MIN_FUZZY_LEN = 5;

const OP_PATTERN = new RegExp(
  `^(${[...FIELD_OPS, ...DATE_OPS].join("|")}):`,
  "i",
);

/** Splits on whitespace but keeps "quoted runs" together, tracking offsets. */
function scan(input: string): { raw: string; start: number }[] {
  const out: { raw: string; start: number }[] = [];
  let i = 0;
  while (i < input.length) {
    while (i < input.length && /\s/.test(input[i])) i++;
    if (i >= input.length) break;
    const start = i;
    let quoted = false;
    while (i < input.length) {
      const ch = input[i];
      if (ch === '"') quoted = !quoted;
      else if (!quoted && /\s/.test(ch)) break;
      i++;
    }
    out.push({ raw: input.slice(start, i), start });
  }
  return out;
}

function isDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function stripQuotes(value: string): string {
  return value.replace(/^"|"$/g, "");
}

export function tokenize(input: string): QueryToken[] {
  return scan(input).map(({ raw, start }) => {
    const end = start + raw.length;
    const base = { raw, start, end };

    const op = raw.match(OP_PATTERN);
    if (op) {
      const name = op[1].toLowerCase();
      const operand = stripQuotes(raw.slice(op[0].length));

      if (name === "before" || name === "after") {
        // An incomplete date (`after:2001-1`) is flagged so the chip can show
        // it is not yet a usable filter instead of silently doing nothing.
        return {
          ...base,
          kind: (isDate(operand) ? "date" : "unknown") as TokenKind,
          value: operand,
          field: undefined,
        };
      }

      const field = name as FieldOp;
      return {
        ...base,
        kind: (operand ? (field === "subject" ? "text" : "person") : "unknown") as TokenKind,
        field,
        value: operand,
      };
    }

    if (raw.startsWith('"')) {
      const value = stripQuotes(raw);
      // An unterminated quote is still being typed; don't call it a phrase yet.
      const closed = raw.length > 1 && raw.endsWith('"');
      return { ...base, kind: (closed ? "phrase" : "unknown") as TokenKind, value };
    }

    return {
      ...base,
      kind: "text" as TokenKind,
      value: raw,
      fuzzy: raw.length >= MIN_FUZZY_LEN,
    };
  });
}

/** Folds tokens into the filter object the API expects. */
export function parse(input: string): ParsedQuery {
  const tokens = tokenize(input);
  const filters: SearchFilters = {};
  const phrases: string[] = [];
  const free: string[] = [];

  for (const t of tokens) {
    if (t.kind === "unknown" || !t.value) continue;

    if (t.kind === "date") {
      // `before:` / `after:` are distinguished by the raw operator text.
      if (/^after:/i.test(t.raw)) filters.after = t.value;
      else filters.before = t.value;
      continue;
    }

    if (t.kind === "phrase") {
      phrases.push(t.value);
      continue;
    }

    if (t.field && t.field !== "subject") {
      const key = t.field;
      filters[key] = [...(filters[key] ?? []), t.value.toLowerCase()];
      continue;
    }

    free.push(t.value);
  }

  // Spelling corrections come from the server's index; the client parser has none.
  return { tokens, free_text: free.join(" "), phrases, filters, corrections: [] };
}

/** True when the query carries no retrievable content (only empty operators). */
export function isEmpty(input: string): boolean {
  const p = parse(input);
  return (
    !p.free_text &&
    p.phrases.length === 0 &&
    Object.keys(p.filters).length === 0
  );
}

/** Merges parsed-from-text filters with facet selections made by clicking. */
export function mergeFilters(a: SearchFilters, b: SearchFilters): SearchFilters {
  const uniq = (xs: string[]) => Array.from(new Set(xs));
  return {
    from: a.from || b.from ? uniq([...(a.from ?? []), ...(b.from ?? [])]) : undefined,
    to: a.to || b.to ? uniq([...(a.to ?? []), ...(b.to ?? [])]) : undefined,
    cc: a.cc || b.cc ? uniq([...(a.cc ?? []), ...(b.cc ?? [])]) : undefined,
    folder:
      a.folder || b.folder ? uniq([...(a.folder ?? []), ...(b.folder ?? [])]) : undefined,
    after: b.after ?? a.after,
    before: b.before ?? a.before,
    has_attachment: b.has_attachment ?? a.has_attachment,
  };
}

/** Drops undefined/empty keys so filters compare and serialise cleanly. */
export function compactFilters(f: SearchFilters): SearchFilters {
  const out: SearchFilters = {};
  if (f.from?.length) out.from = f.from;
  if (f.to?.length) out.to = f.to;
  if (f.cc?.length) out.cc = f.cc;
  if (f.folder?.length) out.folder = f.folder;
  if (f.after) out.after = f.after;
  if (f.before) out.before = f.before;
  if (typeof f.has_attachment === "boolean") out.has_attachment = f.has_attachment;
  if (f.tag?.length) out.tag = f.tag;
  return out;
}

export function countFilters(f: SearchFilters): number {
  const c = compactFilters(f);
  return (
    (c.from?.length ?? 0) +
    (c.to?.length ?? 0) +
    (c.cc?.length ?? 0) +
    (c.folder?.length ?? 0) +
    (c.after ? 1 : 0) +
    (c.before ? 1 : 0) +
    (typeof c.has_attachment === "boolean" ? 1 : 0) +
    (c.tag?.length ?? 0)
  );
}
