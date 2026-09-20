"use client";

/**
 * Month histogram with a drag-to-select date range.
 *
 * A date_histogram aggregation is already in the response, and "when did this
 * happen" is half of what an investigator asks, so the timeline is a control
 * rather than a picture: dragging across it sets after/before and re-runs the
 * search. Clicking the selection clears it.
 */

import { useRef, useState } from "react";
import type { DateBucket } from "@/lib/types";
import { count, monthLabel } from "@/lib/format";

interface Props {
  buckets: DateBucket[];
  after?: string;
  before?: string;
  onRange: (after: string | undefined, before: string | undefined) => void;
  /** Shorter, chrome-free version for the insights panel. */
  compact?: boolean;
}

/** Last day of the month a bucket starts on, so `before:` includes it. */
function endOfMonth(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + 1);
  d.setUTCDate(0);
  return d.toISOString().slice(0, 10);
}

export function Timeline({ buckets, after, before, onRange, compact = false }: Props) {
  const [drag, setDrag] = useState<{ from: number; to: number } | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  if (buckets.length < 2) return null;

  const max = Math.max(...buckets.map((b) => b.doc_count), 1);

  // Which bars fall inside the committed filter, so they can stay lit.
  const selected = (i: number) => {
    const b = buckets[i];
    if (after && b.key_as_string < after) return false;
    if (before && b.key_as_string > before) return false;
    return Boolean(after || before);
  };

  const inDrag = (i: number) =>
    drag !== null && i >= Math.min(drag.from, drag.to) && i <= Math.max(drag.from, drag.to);

  function commit(d: { from: number; to: number }) {
    const lo = Math.min(d.from, d.to);
    const hi = Math.max(d.from, d.to);
    onRange(buckets[lo].key_as_string, endOfMonth(buckets[hi].key_as_string));
  }

  const hasRange = Boolean(after || before);

  return (
    <div className="select-none">
      {!compact && (
        <div className="mb-1.5 flex items-baseline justify-between">
          <h2 className="text-[0.8125rem] font-semibold">Timeline</h2>
          {hasRange ? (
            <button
              onClick={() => onRange(undefined, undefined)}
              className="meta transition-colors hover:text-[var(--color-ink)]"
            >
              Clear dates
            </button>
          ) : (
            <span className="meta">Drag to filter</span>
          )}
        </div>
      )}

      <div
        ref={ref}
        className={compact ? "flex h-9 items-end gap-px" : "flex h-16 items-end gap-px"}
        onPointerLeave={() => {
          setHover(null);
          if (drag) {
            commit(drag);
            setDrag(null);
          }
        }}
        onPointerUp={() => {
          if (drag) {
            commit(drag);
            setDrag(null);
          }
        }}
      >
        {buckets.map((b, i) => {
          const lit = inDrag(i) || (!drag && selected(i));
          const dim = (drag !== null && !inDrag(i)) || (!drag && hasRange && !lit);
          return (
            <button
              key={b.key}
              onPointerDown={(e) => {
                e.preventDefault();
                (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
                setDrag({ from: i, to: i });
              }}
              onPointerEnter={() => {
                setHover(i);
                setDrag((d) => (d ? { ...d, to: i } : null));
              }}
              className="group relative flex h-full flex-1 cursor-ew-resize items-end"
              aria-label={`${monthLabel(b.key_as_string)}, ${count(b.doc_count)} emails`}
            >
              <span
                className="w-full rounded-t-[1px] transition-all duration-200"
                style={{
                  // Zero-count months keep a hairline so gaps stay visible.
                  height: `${Math.max((b.doc_count / max) * 100, b.doc_count ? 6 : 2)}%`,
                  background: lit
                    ? "var(--color-ink)"
                    : dim
                      ? "var(--color-rule)"
                      : "var(--color-rule-strong)",
                  opacity: dim ? 0.7 : 1,
                }}
              />
              {hover === i && (
                <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded bg-[var(--color-ink)] px-2 py-1 text-[0.6875rem] font-medium text-[var(--color-surface)] shadow-[var(--shadow-card)]">
                  {monthLabel(b.key_as_string)}, {count(b.doc_count)} emails
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="meta mt-1 flex justify-between text-[0.6875rem]">
        <span>{monthLabel(buckets[0].key_as_string)}</span>
        {compact && hasRange ? (
          <button
            onClick={() => onRange(undefined, undefined)}
            className="transition-colors hover:text-[var(--color-ink)]"
          >
            Clear
          </button>
        ) : (
          <span>{monthLabel(buckets[buckets.length - 1].key_as_string)}</span>
        )}
      </div>
    </div>
  );
}
