/**
 * Passes browser requests through to the FastAPI search API.
 *
 * Keeping the API host server-side means the cluster address (and any auth
 * header added later) never reaches the client bundle — the same reason
 * config.py exists on the Python side.
 */

import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  const target = `${API_BASE_URL}/${path.join("/")}${req.nextUrl.search}`;

  try {
    const res = await fetch(target, {
      headers: { accept: "application/json" },
      signal: req.signal,
      cache: "no-store",
    });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
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
