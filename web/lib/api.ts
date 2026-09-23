/**
 * The only module that knows whether data comes from the real API or fixtures.
 *
 * NEXT_PUBLIC_USE_MOCK=false talks to the FastAPI service; anything else serves
 * the in-browser fixtures. Nothing else in the app changes. Requests go through /api/proxy/* so the FastAPI
 * host stays server-side.
 */

import type {
  EmailDoc,
  Health,
  SearchParams,
  SearchResponse,
  Suggestion,
  TagCount,
  ThreadResponse,
} from "./types";
import * as mock from "./mock/engine";
import {
  adaptEmail,
  adaptHealth,
  adaptSearch,
  adaptSuggest,
  adaptThread,
} from "./adapt";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";

/** Fixtures resolve instantly; a little latency keeps the loading states honest. */
function settle<T>(value: T, ms: number, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => resolve(value), ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

async function get<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/api/proxy${path}`, { signal });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

async function send<T = unknown>(
  method: "PUT" | "POST" | "PATCH",
  path: string,
  body: unknown,
): Promise<T> {
  const res = await fetch(`/api/proxy${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function toQuery(params: SearchParams): string {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.size) qs.set("size", String(params.size));
  if (params.page_token) qs.set("page_token", params.page_token);
  if (params.rerank) qs.set("rerank", "true");

  const f = params.filters;
  for (const key of ["from", "to", "cc", "folder"] as const) {
    for (const v of f[key] ?? []) qs.append(key, v);
  }
  if (f.after) qs.set("after", f.after);
  if (f.before) qs.set("before", f.before);
  if (typeof f.has_attachment === "boolean") {
    qs.set("has_attachment", String(f.has_attachment));
  }
  for (const t of f.tag ?? []) qs.append("tag", t);
  return qs.toString();
}

/* ------------------------------------------------------------------ tags */

/** Fixture mode has no server to remember tags, so they live here for the session. */
const mockTags = new Map<string, string[]>();

function withMockTags<T extends { id: string; tags: string[] }>(item: T): T {
  return { ...item, tags: mockTags.get(item.id) ?? item.tags };
}

/**
 * Add and remove tags on one email. Applied atomically by the API, so another
 * reviewer's concurrent change to the same email is kept, not overwritten.
 */
export async function changeTags(id: string, add: string[], remove: string[]): Promise<string[]> {
  if (USE_MOCK) {
    const next = new Set(mockTags.get(id) ?? []);
    add.forEach((t) => next.add(t.toLowerCase()));
    remove.forEach((t) => next.delete(t.toLowerCase()));
    const clean = [...next].sort();
    if (clean.length) mockTags.set(id, clean);
    else mockTags.delete(id);
    return settle(clean, 40);
  }
  const res = await send<{ tags: string[] }>("PATCH", `/emails/${encodeURIComponent(id)}/tags`, {
    add,
    remove,
  });
  return res.tags;
}

export async function batchTags(ids: string[], add: string[], remove: string[] = []): Promise<number> {
  if (USE_MOCK) {
    for (const id of ids) {
      const next = new Set(mockTags.get(id) ?? []);
      add.forEach((t) => next.add(t));
      remove.forEach((t) => next.delete(t));
      if (next.size) mockTags.set(id, [...next].sort());
      else mockTags.delete(id);
    }
    return settle(ids.length, 60);
  }
  const res = await send<{ updated: number }>("POST", "/tags/batch", { ids, add, remove });
  return res.updated;
}

export async function listTags(signal?: AbortSignal): Promise<TagCount[]> {
  if (USE_MOCK) {
    const counts = new Map<string, number>();
    for (const tags of mockTags.values()) tags.forEach((t) => counts.set(t, (counts.get(t) ?? 0) + 1));
    const out = [...counts].map(([tag, count]) => ({ tag, count }));
    return settle(out.sort((a, b) => b.count - a.count), 30, signal);
  }
  const res = await get<{ tags: TagCount[] }>("/tags", signal);
  return res.tags;
}

/** Where the browser downloads the current result set as CSV (live API only). */
export function exportUrl(params: SearchParams): string {
  const { page_token: _ignored, size: _size, ...rest } = params;
  return `/api/proxy/export?${toQuery(rest)}`;
}

export async function search(
  params: SearchParams,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  if (USE_MOCK) {
    const result = mock.search(params);
    let hits = result.hits.map(withMockTags);
    const wanted = params.filters.tag ?? [];
    if (wanted.length) hits = hits.filter((h) => h.tags.some((t) => wanted.includes(t)));
    const total = wanted.length ? hits.length : result.total;
    // Reranking really is slow; let the UI show that it is.
    return settle({ ...result, hits, total }, params.rerank ? 220 : 90, signal);
  }
  return adaptSearch(await get(`/search?${toQuery(params)}`, signal));
}

export async function getEmail(id: string, signal?: AbortSignal): Promise<EmailDoc> {
  if (USE_MOCK) {
    const doc = mock.getEmail(id);
    if (!doc) throw new ApiError(404, `No email with id ${id}`);
    return settle(withMockTags(doc), 70, signal);
  }
  return adaptEmail(await get(`/emails/${encodeURIComponent(id)}`, signal));
}

export async function getThread(id: string, signal?: AbortSignal): Promise<ThreadResponse> {
  if (USE_MOCK) {
    const t = mock.getThread(id);
    if (!t) throw new ApiError(404, `No thread with id ${id}`);
    return settle(t, 90, signal);
  }
  return adaptThread(await get(`/threads/${encodeURIComponent(id)}`, signal));
}

export async function suggest(prefix: string, signal?: AbortSignal): Promise<Suggestion[]> {
  if (USE_MOCK) return settle(mock.suggest(prefix), 40, signal);
  return adaptSuggest(await get(`/suggest?prefix=${encodeURIComponent(prefix)}`, signal));
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  if (USE_MOCK) return settle(mock.health(), 120, signal);
  return adaptHealth(await get("/health", signal));
}

export const isMock = USE_MOCK;
