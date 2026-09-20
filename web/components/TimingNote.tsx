"use client";

/**
 * How long the search took, and where the time went.
 *
 * The API returns a per-stage breakdown on every response and the spec asks
 * for a timing panel, so it sits in the open: on this product "why is this
 * slow" is a question the operator asks constantly.
 */

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Timing } from "@/lib/types";
import { ms } from "@/lib/format";
import { isMock } from "@/lib/api";

const COLOURS: Record<string, string> = {
  parse: "var(--color-rule-strong)",
  "keyword (BM25)": "var(--color-marker-key-solid)",
  "vector (kNN)": "var(--color-marker-sem-solid)",
  fusion: "var(--color-faint)",
  rerank: "#c08a2e",
  highlight: "#b9b4ab",
  facets: "#8e8981",
};

export function TimingNote({ timing }: { timing: Timing }) {
  const [open, setOpen] = useState(false);

  const stages = (
    [
      ["parse", timing.parse_ms],
      ["keyword (BM25)", timing.bm25_ms],
      ["vector (kNN)", timing.vector_ms],
      ["fusion", timing.fusion_ms],
      ["rerank", timing.rerank_ms ?? 0],
      ["highlight", timing.highlight_ms],
      ["facets", timing.facets_ms],
    ] as const
  ).filter(([, v]) => v > 0);

  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="meta num rounded-full border border-[var(--color-rule)] px-3 py-1 transition-colors hover:border-[var(--color-rule-strong)] hover:text-[var(--color-ink)]"
      >
        {ms(timing.total_ms)}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 top-[calc(100%+8px)] z-40 w-[270px] rounded-xl border border-[var(--color-rule)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-pill-lift)]"
          >
            <p className="mb-2 text-[0.8125rem] font-semibold">
              Search took {ms(timing.total_ms)}
            </p>
            <div className="flex h-1.5 overflow-hidden rounded-full bg-[var(--color-sunk)]">
              {stages.map(([name, value]) => (
                <span
                  key={name}
                  title={`${name} ${ms(value)}`}
                  style={{
                    width: `${(value / timing.total_ms) * 100}%`,
                    background: COLOURS[name],
                  }}
                />
              ))}
            </div>
            <dl className="mt-2.5 space-y-1 text-[0.75rem]">
              {stages.map(([name, value]) => (
                <div key={name} className="flex items-center gap-2">
                  <span
                    className="size-1.5 shrink-0 rounded-full"
                    style={{ background: COLOURS[name] }}
                    aria-hidden
                  />
                  <dt className="flex-1 text-[var(--color-muted)]">{name}</dt>
                  <dd className="num">{ms(value)}</dd>
                </div>
              ))}
            </dl>
            {isMock && (
              <p className="mt-3 border-t border-[var(--color-rule)] pt-2.5 text-[0.75rem] text-[var(--color-muted)]">
                Sample data. Set NEXT_PUBLIC_USE_MOCK=false to search the real cluster.
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
