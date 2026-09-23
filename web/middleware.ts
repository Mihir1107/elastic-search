/**
 * Optional sign-in for the whole app, and the reviewer name tags are saved under.
 *
 * With LEDGER_BASIC_AUTH="alice:pw1,bob:pw2" every page and API call needs one
 * of those logins (HTTP basic auth — serve it behind TLS). The signed-in name
 * is passed to the API as X-Ledger-User so a tag records who made it. Unset,
 * the app is open, which is only reasonable on localhost.
 *
 * Whatever the browser sends as X-Ledger-User is always discarded first, so
 * nobody can tag under someone else's name.
 */

import { NextRequest, NextResponse } from "next/server";

const USERS = new Map(
  (process.env.LEDGER_BASIC_AUTH ?? "")
    .split(",")
    .map((pair) => pair.trim())
    .filter((pair) => pair.includes(":"))
    .map((pair) => {
      const at = pair.indexOf(":");
      return [pair.slice(0, at), pair.slice(at + 1)] as const;
    }),
);

/** Compares in time independent of where the strings first differ. */
function same(a: string, b: string): boolean {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

function signedIn(req: NextRequest): string | null {
  const header = req.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) return null;
  let decoded: string;
  try {
    decoded = atob(header.slice(6));
  } catch {
    return null;
  }
  const at = decoded.indexOf(":");
  if (at < 0) return null;
  const user = decoded.slice(0, at);
  const expected = USERS.get(user);
  return expected !== undefined && same(decoded.slice(at + 1), expected) ? user : null;
}

export function middleware(req: NextRequest) {
  const headers = new Headers(req.headers);
  headers.delete("x-ledger-user");

  if (USERS.size) {
    const user = signedIn(req);
    if (!user) {
      return new NextResponse("Sign in to Ledger", {
        status: 401,
        headers: { "www-authenticate": 'Basic realm="Ledger", charset="UTF-8"' },
      });
    }
    headers.set("x-ledger-user", user);
  }
  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Everything except Next's own static assets.
  matcher: ["/((?!_next/static|_next/image|icon.svg).*)"],
};
