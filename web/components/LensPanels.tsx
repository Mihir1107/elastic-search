"use client";

/**
 * The non-email lenses: people, dates, topics and attachments.
 *
 * Each is a different cut of the same aggregations, and each row filters the
 * search rather than navigating away — the question "who talked about this, and
 * when" is answered by moving between these, not by starting over.
 */

import { motion } from "motion/react";
import type { EmailHit, Facets, SearchFilters } from "@/lib/types";
import { count, monthLabel, personName, plural, shortDate } from "@/lib/format";
import { Avatar } from "./Avatar";

const EASE = [0.22, 1, 0.36, 1] as const;

function Wrap({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: EASE }}
      className="card overflow-hidden"
    >
      {children}
    </motion.div>
  );
}

export function PeopleLens({
  facets,
  filters,
  onToggle,
}: {
  facets: Facets;
  filters: SearchFilters;
  onToggle: (key: keyof SearchFilters, value: string) => void;
}) {
  const max = Math.max(...facets.senders.map((b) => b.doc_count), 1);

  return (
    <Wrap>
      {facets.senders.map((b) => {
        const on = filters.from?.some((f) => b.key.includes(f)) ?? false;
        return (
          <button
            key={b.key}
            onClick={() => onToggle("from", b.key)}
            aria-pressed={on}
            className="result flex w-full items-center gap-3 px-4 py-3 text-left"
            data-active={on}
          >
            <Avatar address={b.key} name={b.label} size={32} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[0.875rem] font-medium">
                {b.label ?? personName(b.key)}
              </span>
              <span className="meta block truncate text-[0.75rem]">{b.key}</span>
            </span>
            <span className="hidden w-32 shrink-0 sm:block">
              <span
                className="block h-1.5 rounded-full bg-[var(--color-rule-strong)]"
                style={{ width: `${Math.max((b.doc_count / max) * 100, 4)}%` }}
              />
            </span>
            <span className="num shrink-0 text-[0.8125rem] text-[var(--color-muted)]">
              {plural(b.doc_count, "email")}
            </span>
          </button>
        );
      })}
    </Wrap>
  );
}

export function DatesLens({
  facets,
  onRange,
}: {
  facets: Facets;
  onRange: (after: string | undefined, before: string | undefined) => void;
}) {
  const months = facets.date_histogram.filter((b) => b.doc_count > 0);
  const max = Math.max(...months.map((b) => b.doc_count), 1);

  function endOfMonth(iso: string): string {
    const d = new Date(`${iso}T00:00:00Z`);
    d.setUTCMonth(d.getUTCMonth() + 1);
    d.setUTCDate(0);
    return d.toISOString().slice(0, 10);
  }

  return (
    <Wrap>
      {months.map((b) => (
        <button
          key={b.key}
          onClick={() => onRange(b.key_as_string, endOfMonth(b.key_as_string))}
          className="result flex w-full items-center gap-4 px-4 py-3 text-left"
        >
          <span className="w-20 shrink-0 text-[0.875rem] font-medium">
            {monthLabel(b.key_as_string)}
          </span>
          <span className="min-w-0 flex-1">
            <span
              className="block h-2 rounded-full bg-[var(--color-rule-strong)] transition-[width] duration-300"
              style={{ width: `${Math.max((b.doc_count / max) * 100, 3)}%` }}
            />
          </span>
          <span className="num shrink-0 text-[0.8125rem] text-[var(--color-muted)]">
            {count(b.doc_count)}
          </span>
        </button>
      ))}
    </Wrap>
  );
}

export function TopicsLens({
  facets,
  filters,
  onToggle,
}: {
  facets: Facets;
  filters: SearchFilters;
  onToggle: (key: keyof SearchFilters, value: string) => void;
}) {
  const buckets = facets.topics.length ? facets.topics : facets.folders;
  const max = Math.max(...buckets.map((b) => b.doc_count), 1);

  return (
    <Wrap>
      {buckets.map((b) => {
        const on = filters.folder?.includes(b.key) ?? false;
        return (
          <button
            key={b.key}
            onClick={() => onToggle("folder", b.key)}
            aria-pressed={on}
            data-active={on}
            className="result flex w-full items-center gap-4 px-4 py-3 text-left"
          >
            <span className="min-w-0 flex-1 truncate text-[0.875rem] font-medium">{b.key}</span>
            <span className="hidden w-40 shrink-0 sm:block">
              <span
                className="block h-1.5 rounded-full bg-[var(--color-rule-strong)]"
                style={{ width: `${Math.max((b.doc_count / max) * 100, 4)}%` }}
              />
            </span>
            <span className="num shrink-0 text-[0.8125rem] text-[var(--color-muted)]">
              {count(b.doc_count)}
            </span>
          </button>
        );
      })}
    </Wrap>
  );
}

export function AttachmentsLens({
  hits,
  onOpen,
}: {
  hits: EmailHit[];
  onOpen: (h: EmailHit) => void;
}) {
  const withFiles = hits.filter((h) => h.attachment_names.length > 0);

  if (!withFiles.length) {
    return (
      <Wrap>
        <div className="px-6 py-12 text-center">
          <p className="font-serif text-[1.125rem]">No attachments on this page</p>
          <p className="meta mx-auto mt-1.5 max-w-[42ch]">
            The corpus records attachment names, not the files. Load more results to
            look further down the list.
          </p>
        </div>
      </Wrap>
    );
  }

  return (
    <Wrap>
      {withFiles.map((h) => (
        <button
          key={h.id}
          onClick={() => onOpen(h)}
          className="result flex w-full items-center gap-3 px-4 py-3 text-left"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[0.875rem] font-medium">
              {h.attachment_names.join(", ")}
            </span>
            <span className="meta block truncate text-[0.75rem]">
              {h.subject} — {h.from_name || personName(h.from)}
            </span>
          </span>
          <time className="meta num shrink-0 text-[0.75rem]" dateTime={h.date}>
            {shortDate(h.date)}
          </time>
        </button>
      ))}
    </Wrap>
  );
}
