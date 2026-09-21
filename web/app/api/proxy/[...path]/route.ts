/**
 * Passes browser requests through to the FastAPI search API.
 *
 * Keeping the API host server-side means the cluster address (and any auth
 * header added later) never reaches the client bundle — the same reason
 * config.py exists on the Python side.
 */

import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

/** Response headers worth forwarding: the body type, and what an export download needs. */
const PASS_HEADERS = [
  "content-type",
  "content-disposition",
  "x-ledger-export-mode",
  "x-ledger-export-truncated",
];

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${API_BASE_URL}/${path.join("/")}${req.nextUrl.search}`;
  const hasBody = req.method === "PUT" || req.method === "POST";

  try {
    const res = await fetch(target, {
      method: req.method,
      headers: {
        accept: req.headers.get("accept") ?? "application/json",
        ...(hasBody ? { "content-type": "application/json" } : {}),
      },
      body: hasBody ? await req.text() : undefined,
      signal: req.signal,
      cache: "no-store",
    });
    const headers = new Headers();
    for (const name of PASS_HEADERS) {
      const value = res.headers.get(name);
      if (value) headers.set(name, value);
    }
    if (!headers.has("content-type")) headers.set("content-type", "application/json");
    // Streamed through, so a large CSV export never has to fit in memory here.
    return new NextResponse(res.body, { status: res.status, headers });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      // The browser cancelled an in-flight search; not an error worth reporting.
      return new NextResponse(null, { status: 499 });
    }
    return NextResponse.json(
      { detail: `Search API unreachable at ${API_BASE_URL}. Is it running?` },
      { status: 502 },
    );
  }
}

export const GET = forward;
export const PUT = forward;
export const POST = forward;
