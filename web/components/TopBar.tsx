"use client";

/**
 * Landing header: wordmark, the three places this app has, and cluster state.
 *
 * "Index up to date" is live health, not decoration — it reads the same
 * /health endpoint the operator would curl, so a yellow cluster or an
 * unreachable API is visible from the front door.
 */

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import type { Health } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";

export function IndexPill({ compact = false }: { compact?: boolean }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const ac = new AbortController();
    getHealth(ac.signal)
      .then(setHealth)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== "AbortError") setFailed(true);
      });
    return () => ac.abort();
  }, []);

  const colour = failed
    ? "var(--color-faint)"
    : health?.cluster.status === "green"
      ? "var(--color-live)"
      : health
        ? "#c08a2e"
        : "var(--color-rule-strong)";

  const label = failed
    ? "Search API unreachable"
    : !health
      ? "Checking index"
      : health.cluster.status === "green"
        ? "Index up to date"
        : `Cluster ${health.cluster.status}`;

  const detail = health
    ? `${health.cluster.number_of_nodes} nodes, ${health.license} license, ${health.index}`
    : undefined;

  return (
    <span
      title={detail}
      className={[
        "inline-flex items-center gap-2 rounded-full border border-[var(--color-rule)]",
        "bg-[var(--color-surface)] text-[0.8125rem] text-[var(--color-muted)]",
        compact ? "px-2.5 py-1" : "px-3 py-1.5",
      ].join(" ")}
    >
      <span className="size-2 shrink-0 rounded-full" style={{ background: colour }} aria-hidden />
      {label}
    </span>
  );
}

export function TopBar() {
  return (
    <header className="relative z-20 flex items-center px-6 py-5 sm:px-9">
      <span className="font-serif text-[1.45rem] tracking-[-0.01em]">Ledger</span>

      <nav className="absolute left-1/2 hidden -translate-x-1/2 gap-8 text-[0.875rem] md:flex">
        <span className="font-medium">Search</span>
        <span className="text-[var(--color-faint)]">Collections</span>
        <span className="text-[var(--color-faint)]">History</span>
      </nav>

      <div className="ml-auto flex items-center gap-3">
        <span className="hidden sm:block">
          <IndexPill />
        </span>
        <ThemeToggle />
        <span
          className="grid size-8 place-items-center rounded-full bg-[var(--color-dark)] text-[0.8125rem] font-semibold text-surface"
          title="Signed in as the local operator"
        >
          M
        </span>
      </div>
    </header>
  );
}
