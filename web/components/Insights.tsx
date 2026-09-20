"use client";

/**
 * What the result set is made of.
 *
 * Every number here comes from an aggregation over the whole match, not the
 * page on screen, and every row is a filter: clicking a person narrows to them.
 * The same filters go to both retrieval legs on the server, so the panel always
 * describes the set you are actually looking at.
 */

import { AnimatePresence, motion } from "motion/react";
import type { Facets, SearchFilters } from "@/lib/types";
import { count, monthLabel, personName, plural } from "@/lib/format";
import { Avatar } from "./Avatar";
import { Timeline } from "./Timeline";

interface Props {
  facets: Facets;
  filters: SearchFilters;
  total: number;
  onToggle: (key: keyof SearchFilters, value: string) => void;
  onRange: (after: string | undefined, before: string | undefined) => void;
  onAttachments: (value: boolean | undefined) => void;
}

export function Insights({
  facets,
  filters,
  total,
  onToggle,
  onRange,
  onAttachments,
}: Props) {
  const months = facets.date_histogram.filter((b) => b.doc_count > 0);
  const span =
    months.length > 1
      ? `${monthLabel(months[0].key_as_string)} to ${monthLabel(
          months[months.length - 1].key_as_string,
        )}`
      : months.length === 1
        ? monthLabel(months[0].key_as_string)
        : null;

  const topics = facets.topics.length ? facets.topics : facets.folders;
  const topicHeading = facets.topics.length ? "Key topics" : "Folders";
  const topicKey: keyof SearchFilters = facets.topics.length ? "folder" : "folder";

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <h2 className="flex items-center gap-2 text-[0.9375rem] font-semibold">
          <Sparkle />
          Insights
        </h2>

        <Section title="People">
          <div className="space-y-0.5">
            {facets.senders.slice(0, 4).map((b) => {
              const on = filters.from?.some((f) => b.key.includes(f)) ?? false;
              return (
                <button
                  key={b.key}
                  onClick={() => onToggle("from", b.key)}
                  aria-pressed={on}
                  className={[
                    "flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left transition-colors",
                    on ? "bg-[var(--color-sunk)]" : "hover:bg-[var(--color-sunk)]",
                  ].join(" ")}
                >
                  <Avatar address={b.key} name={b.label} size={28} />
                  <span
                    className={[
                      "min-w-0 flex-1 truncate text-[0.875rem]",
                      on ? "font-semibold" : "",
                    ].join(" ")}
                  >
                    {b.label ?? personName(b.key)}
                  </span>
                  <span className="meta num shrink-0 text-[0.75rem]">
                    {count(b.doc_count)}
                  </span>
                </button>
              );
            })}
          </div>
        </Section>

        {topics.length > 0 && (
          <Section title={topicHeading}>
            <div className="flex flex-wrap gap-1.5">
              <AnimatePresence initial={false}>
                {topics.slice(0, 8).map((b) => {
                  const on = filters.folder?.includes(b.key) ?? false;
                  return (
                    <motion.button
                      key={b.key}
                      layout
                      initial={{ opacity: 0, scale: 0.94 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.94 }}
                      transition={{ duration: 0.16 }}
                      onClick={() => onToggle(topicKey, b.key)}
                      aria-pressed={on}
                      // The selected pill's colour is set inline, the same way
                      // Tabs.tsx does it: this element already carries a
                      // `text-[0.75rem]` utility, and adding a second `text-*`
                      // for the colour produced no rule at all, leaving ink text
                      // on an ink background.
                      style={on ? { color: "var(--color-surface)" } : undefined}
                      className={[
                        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[0.75rem] transition-colors",
                        on
                          ? "border-[var(--color-ink)] bg-[var(--color-ink)]"
                          : "border-[var(--color-rule)] hover:border-[var(--color-rule-strong)]",
                      ].join(" ")}
                    >
                      {b.key}
                      <span className="num opacity-60">{b.doc_count}</span>
                    </motion.button>
                  );
                })}
              </AnimatePresence>
            </div>
          </Section>
        )}

        {span && (
          <Section title="Date range">
            <p className="text-[0.875rem]">{span}</p>
            <div className="mt-2.5">
              <Timeline
                buckets={facets.date_histogram}
                after={filters.after}
                before={filters.before}
                onRange={onRange}
                compact
              />
            </div>
          </Section>
        )}

        <Section title="Attachments">
          <button
            onClick={() =>
              onAttachments(filters.has_attachment === true ? undefined : true)
            }
            aria-pressed={filters.has_attachment === true}
            className={[
              "w-full rounded-lg px-1.5 py-1.5 text-left text-[0.875rem] transition-colors",
              filters.has_attachment === true
                ? "bg-[var(--color-sunk)] font-semibold"
                : "hover:bg-[var(--color-sunk)]",
            ].join(" ")}
          >
            {facets.attachments.with > 0
              ? `${plural(facets.attachments.with, "email")} with files`
              : "No attachments in these results"}
          </button>
        </Section>
      </div>

      {/* One quiet editorial note, the only decoration on the page. */}
      <figure className="rounded-xl bg-[var(--color-sunk)] px-5 py-5">
        <blockquote className="font-serif text-[1.0625rem] leading-snug">
          The right context turns information into clarity.
        </blockquote>
        <figcaption className="mt-3 h-px w-8 bg-[var(--color-rule-strong)]" />
      </figure>

      <p className="meta px-1 text-[var(--color-faint)]">
        Counts are aggregated over all {count(total)} matches, not just this page.
      </p>
    </div>
  );
}

/** Sections settle in order rather than all at once, so the panel reads
 *  top-down the way it is meant to be scanned. The stagger is CSS
 *  (`nth-of-type` delays in globals.css) rather than a render-order counter,
 *  which would be wrong the moment React renders this twice concurrently. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="insight-section mt-5 border-t border-[var(--color-rule)] pt-4 first-of-type:mt-4">
      <h3 className="mb-2 text-[0.8125rem] font-semibold text-[var(--color-muted)]">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Sparkle() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 1.5l1.5 4L13.5 7l-4 1.5L8 12.5 6.5 8.5 2.5 7l4-1.5L8 1.5z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M12.8 11.2l.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6.6-1.6z" fill="currentColor" />
    </svg>
  );
}
