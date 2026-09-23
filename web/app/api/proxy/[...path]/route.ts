/**
 * Passes browser requests through to the FastAPI search API.
 *
 * Keeping the API host server-side means the cluster address and the API key
 * never reach the client bundle — the same reason config.py exists on the
 * Python side.
 *
 * Writes are guarded against cross-site request forgery. A page on any other
 * site can make a browser POST here with a `text/plain` form (a "simple"
 * request, sent without a CORS preflight), and forwarding that body as JSON
 * would let it rewrite review tags. So a write must be JSON, and must come from
 * this origin.
 */

import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
/** Server-side only; sent as X-API-Key when the API requires one. */
const API_KEY = process.env.LEDGER_API_KEY ?? "";
/** Long enough for a large export to start streaming, short enough to fail. */
const UPSTREAM_TIMEOUT_MS = 60_000;
const MAX_BODY_BYTES = 256 * 1024;

/** Response headers worth forwarding: the body type, and what an export download needs. */
const PASS_HEADERS = [
  "content-type",
  "content-disposition",
  "x-ledger-export-mode",
  "x-ledger-export-truncated",
];

const WRITE_METHODS = new Set(["PUT", "POST", "PATCH"]);

function refuse(status: number, detail: string) {
  return NextResponse.json({ detail }, { status });
}

/** True when a write demonstrably came from this app's own pages. */
function sameOrigin(req: NextRequest): boolean {
  const site = req.headers.get("sec-fetch-site");
  if (site) return site === "same-origin";
  // Older browsers: fall back to Origin, which every cross-site POST carries.
  const origin = req.headers.get("origin");
  return origin === null || origin === req.nextUrl.origin;
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const isWrite = WRITE_METHODS.has(req.method);

  if (isWrite) {
    const type = (req.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
    if (type !== "application/json") return refuse(415, "writes must be application/json");
    if (!sameOrigin(req)) return refuse(403, "cross-site write refused");
  }

  // Segments arrive decoded; re-encode each so "%3F" or "%2F" inside an id
  // stays part of that id instead of becoming a query string or a new path.
  const target = `${API_BASE_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  let body: string | undefined;
  if (isWrite) {
    body = await req.text();
    if (body.length > MAX_BODY_BYTES) return refuse(413, "request body too large");
  }

  const headers: Record<string, string> = {
    accept: req.headers.get("accept") ?? "application/json",
  };
  if (isWrite) headers["content-type"] = "application/json";
  if (API_KEY) headers["x-api-key"] = API_KEY;
  // Set by middleware.ts after basic auth; attributes review tags to a person.
  const user = req.headers.get("x-ledger-user");
  if (user) headers["x-ledger-user"] = user;

  try {
    const res = await fetch(target, {
      method: req.method,
      headers,
      body,
      signal: AbortSignal.any([req.signal, AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)]),
      cache: "no-store",
    });
    const out = new Headers();
    for (const name of PASS_HEADERS) {
      const value = res.headers.get(name);
      if (value) out.set(name, value);
    }
    if (!out.has("content-type")) out.set("content-type", "application/json");
    // Streamed through, so a large CSV export never has to fit in memory here.
    return new NextResponse(res.body, { status: res.status, headers: out });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      // The browser cancelled an in-flight search; not an error worth reporting.
      return new NextResponse(null, { status: 499 });
    }
    if (err instanceof Error && err.name === "TimeoutError") {
      return refuse(504, "The search API took too long to answer.");
    }
    // Deliberately vague: the API's address is server-side configuration.
    return refuse(502, "The search API is unreachable. Is it running?");
  }
}

export const GET = forward;
export const PUT = forward;
export const POST = forward;
export const PATCH = forward;
