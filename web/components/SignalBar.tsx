"use client";

/**
 * Two stacked bars showing which retrieval legs found this result.
 *
 * This is the honest version of a relevance score: a hit only the vector leg
 * returned looks visibly different from one both legs agreed on, which is what
 * an investigator needs to judge a result. The live API reports which legs
 * matched rather than the rank inside each, so the bar is read as presence
 * first and depth second — the tooltip says which it is.
 */

import type { HitSignals } from "@/lib/types";

/** Rank 1 fills the bar; deep ranks taper off. */
function fill(rank: number | null): number {
  if (rank === null) return 0;
  return Math.max(0.12, 1 - Math.log10(rank) / 2);
}

export function SignalBar({ signals, delay = 0 }: { signals: HitSignals; delay?: number }) {
  const legs = [
    { key: "keyword", rank: signals.bm25_rank, color: "var(--color-marker-key-solid)" },
    { key: "meaning", rank: signals.vector_rank, color: "var(--color-marker-sem-solid)" },
  ];

  const found = legs.filter((l) => l.rank !== null);
  const label = found.length
    ? `Matched by ${found.map((l) => l.key).join(" and ")}`
    : "No retrieval signal";

  return (
    <span className="signal" title={label} aria-label={label} role="img">
      {legs.map((l) => (
        <i key={l.key}>
          <span
            style={{
              width: `${fill(l.rank) * 100}%`,
              background: l.color,
              animationDelay: `${delay}ms`,
            }}
          />
        </i>
      ))}
    </span>
  );
}
