"use client";

/**
 * Results-view navigation.
 *
 * Saved and History are real and local: starred emails and recent searches live
 * in this browser (see lib/useLocal.ts). There are no user accounts in this
 * build — an explicit non-goal — so nothing is stored server-side and nothing
 * follows you to another machine. Collections would need that, so it is present
 * but honest about being unavailable.
 */

import type { View } from "@/lib/useLocal";
import type { Health } from "@/lib/types";
import { count } from "@/lib/format";

const ITEMS: { id: View; label: string; icon: React.ReactNode; ready: boolean }[] = [
  { id: "search", label: "Search", ready: true, icon: <IconSearch /> },
  { id: "saved", label: "Saved", ready: true, icon: <IconBookmark /> },
  { id: "history", label: "History", ready: true, icon: <IconClock /> },
  { id: "collections", label: "Collections", ready: false, icon: <IconFolder /> },
];

export function Sidebar({
  view,
  onView,
  savedCount,
  health,
  onHome,
}: {
  view: View;
  onView: (v: View) => void;
  savedCount: number;
  health: Health | null;
  onHome: () => void;
}) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-[226px] shrink-0 flex-col border-r border-[var(--color-rule)] px-4 py-6 lg:flex">
      <button
        onClick={onHome}
        className="px-2 text-left font-serif text-[1.45rem] tracking-[-0.01em] transition-opacity hover:opacity-70"
      >
        Ledger
      </button>

      <nav className="mt-7 space-y-0.5">
        {ITEMS.map((item) => {
          const active = view === item.id;
          return (
            <button
              key={item.id}
              onClick={() => item.ready && onView(item.id)}
              disabled={!item.ready}
              title={item.ready ? undefined : "Needs an account, which this build does not have"}
              aria-current={active ? "page" : undefined}
              className={[
                "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[0.9375rem] transition-colors",
                active
                  ? "bg-[var(--color-sunk)] font-semibold"
                  : item.ready
                    ? "text-[var(--color-muted)] hover:bg-[var(--color-sunk)] hover:text-[var(--color-ink)]"
                    : "cursor-not-allowed text-[var(--color-faint)] opacity-60",
              ].join(" ")}
            >
              <span className="shrink-0">{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              {item.id === "saved" && savedCount > 0 && (
                <span className="num text-[0.75rem] text-[var(--color-muted)]">{savedCount}</span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto space-y-1 px-3 pt-8 text-[0.8125rem] text-[var(--color-muted)]">
        <p className="flex items-center gap-2">
          <span
            className="size-2 shrink-0 rounded-full"
            style={{
              background:
                health?.cluster.status === "green"
                  ? "var(--color-live)"
                  : health
                    ? "#c08a2e"
                    : "var(--color-rule-strong)",
            }}
            aria-hidden
          />
          {health?.cluster.status === "green"
            ? "Index up to date"
            : health
              ? `Cluster ${health.cluster.status}`
              : "Checking index"}
        </p>
        {health && health.docs > 0 && <p className="num">{count(health.docs)} emails</p>}
        {health && (
          <p className="text-[var(--color-faint)]">
            {health.cluster.number_of_nodes} nodes, {health.license}
          </p>
        )}
      </div>
    </aside>
  );
}

function IconSearch() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden>
      <circle cx="8" cy="8" r="5.3" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12.2 12.2L16 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconBookmark() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M4.5 2.8h9a1 1 0 011 1v11.4l-5.5-3.4-5.5 3.4V3.8a1 1 0 011-1z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconClock() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden>
      <circle cx="9" cy="9" r="6.6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M9 5.2V9l2.6 1.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconFolder() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M2.6 5.2a1 1 0 011-1h3l1.4 1.8h6.4a1 1 0 011 1v6.8a1 1 0 01-1 1h-11a1 1 0 01-1-1V5.2z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}
