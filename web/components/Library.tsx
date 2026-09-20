"use client";

/**
 * Saved emails and recent searches.
 *
 * Both are per-browser (lib/useLocal.ts) because this build has no accounts.
 * The empty states say what to do rather than just reporting emptiness.
 */

import { motion } from "motion/react";
import type { HistoryEntry, SavedEmail } from "@/lib/useLocal";
import { count, personName, shortDate } from "@/lib/format";
import { Avatar } from "./Avatar";

const EASE = [0.22, 1, 0.36, 1] as const;

function Shell({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.24, ease: EASE }}
      className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-7"
    >
      <h1 className="font-serif text-[2rem] leading-tight tracking-[-0.02em]">{title}</h1>
      <p className="meta mt-1">{note}</p>
      <div className="mt-6">{children}</div>
    </motion.div>
  );
}

function Blank({ headline, body }: { headline: string; body: string }) {
  return (
    <div className="card px-6 py-14 text-center">
      <p className="font-serif text-[1.25rem]">{headline}</p>
      <p className="meta mx-auto mt-2 max-w-[44ch]">{body}</p>
    </div>
  );
}

export function SavedView({
  saved,
  onOpen,
  onRemove,
}: {
  saved: SavedEmail[];
  onOpen: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <Shell
      title="Saved"
      note="Kept in this browser only — this build has no accounts."
    >
      {saved.length === 0 ? (
        <Blank
          headline="Nothing saved yet"
          body="Star a result to keep it here while you work through a question."
        />
      ) : (
        <div className="card overflow-hidden">
          {saved.map((s) => (
            <div key={s.id} className="result flex items-center gap-3 px-4 py-3">
              <Avatar address={s.from} name={s.from_name} size={32} />
              <button onClick={() => onOpen(s.id)} className="min-w-0 flex-1 text-left">
                <span className="block truncate text-[0.9375rem] font-semibold">
                  {s.subject}
                </span>
                <span className="meta block truncate text-[0.75rem]">
                  {s.from_name || personName(s.from)}, {shortDate(s.date)}
                </span>
              </button>
              <button
                onClick={() => onRemove(s.id)}
                className="meta shrink-0 transition-colors hover:text-[var(--color-ink)]"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}

export function HistoryView({
  history,
  onRun,
  onClear,
}: {
  history: HistoryEntry[];
  onRun: (q: string) => void;
  onClear: () => void;
}) {
  return (
    <Shell title="History" note="Recent searches from this browser.">
      {history.length === 0 ? (
        <Blank
          headline="No searches yet"
          body="Every search you run is listed here so you can pick a thread back up."
        />
      ) : (
        <>
          <div className="card overflow-hidden">
            {history.map((h) => (
              <button
                key={`${h.q}-${h.at}`}
                onClick={() => onRun(h.q)}
                className="result flex w-full items-center gap-4 px-4 py-3 text-left"
              >
                <span className="min-w-0 flex-1 truncate text-[0.9375rem]">{h.q}</span>
                <span className="meta num shrink-0 text-[0.75rem]">
                  {count(h.total)} results
                </span>
              </button>
            ))}
          </div>
          <button
            onClick={onClear}
            className="meta mt-4 transition-colors hover:text-[var(--color-ink)]"
          >
            Clear history
          </button>
        </>
      )}
    </Shell>
  );
}

export function CollectionsView() {
  return (
    <Shell
      title="Collections"
      note="Grouping saved emails into named sets."
    >
      <Blank
        headline="Not in this build"
        body="Collections are shared between people, which needs user accounts — an explicit non-goal for the MVP. Saved emails work today and stay in this browser."
      />
    </Shell>
  );
}
