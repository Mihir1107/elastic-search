/**
 * The only module that knows whether data comes from the real API or fixtures.
 *
 * Set NEXT_PUBLIC_USE_MOCK=false once the Phase 2 endpoints are live; nothing
 * else in the app changes. Requests go through /api/proxy/* so the FastAPI
 * host stays server-side.
 */

import type {
  EmailDoc,
  Health,
  SearchParams,
  SearchResponse,
  Suggestion,
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
  return qs.toString();
}

export async function search(
  params: SearchParams,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  if (USE_MOCK) {
    const result = mock.search(params);
    // Reranking really is slow; let the UI show that it is.
    return settle(result, params.rerank ? 220 : 90, signal);
  }
  return adaptSearch(await get(`/search?${toQuery(params)}`, signal));
}

export async function getEmail(id: string, signal?: AbortSignal): Promise<EmailDoc> {
  if (USE_MOCK) {
    const doc = mock.getEmail(id);
    if (!doc) throw new ApiError(404, `No email with id ${id}`);
    return settle(doc, 70, signal);
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
