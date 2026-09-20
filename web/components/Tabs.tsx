"use client";

/**
 * Facet tabs over the result set.
 *
 * These are lenses on one search, not separate searches: the counts all come
 * from aggregations on the same response, so switching never costs a request.
 */

import { motion } from "motion/react";
import { count } from "@/lib/format";

export type Lens = "emails" | "people" | "dates" | "topics" | "attachments";

export interface LensCount {
  id: Lens;
  label: string;
  n: number;
}

export function Tabs({
  lenses,
  active,
  onChange,
}: {
  lenses: LensCount[];
  active: Lens;
  onChange: (l: Lens) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="tablist">
      {lenses.map((l) => {
        const on = l.id === active;
        return (
          <button
            key={l.id}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(l.id)}
            // The active colour is set inline: two `text-[...]` utilities on one
            // element (size and colour) do not reliably both survive the build.
            style={{ color: on ? "var(--color-surface)" : undefined }}
            className={[
              "relative flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[0.875rem] transition-colors",
              on ? "" : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
            ].join(" ")}
          >
            {on && (
              <motion.span
                layoutId="lens-pill"
                className="absolute inset-0 rounded-full bg-[var(--color-dark)]"
                transition={{ type: "spring", stiffness: 420, damping: 36 }}
              />
            )}
            <span className="relative">{l.label}</span>
            <span className={["num relative text-[0.75rem]", on ? "opacity-70" : "opacity-55"].join(" ")}>
              {count(l.n)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
