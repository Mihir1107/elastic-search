"use client";

/**
 * The results view.
 *
 * Three columns at full width — what matched, the one you are reading, and what
 * the set is made of. Below xl the insights fold away, and below lg the reading
 * pane becomes an overlay, because on a phone the list is the thing.
 */

import { AnimatePresence, motion } from "motion/react";
import { SearchPill } from "./SearchPill";
import { Tabs, type Lens, type LensCount } from "./Tabs";
import { ResultList } from "./ResultList";
import { ReadingPane } from "./ReadingPane";
import { Insights } from "./Insights";
import { AttachmentsLens, DatesLens, PeopleLens, TopicsLens } from "./LensPanels";
import { ThemeToggle } from "./ThemeToggle";
import { TimingNote } from "./TimingNote";
import type { EmailHit, SearchFilters, SearchResponse } from "@/lib/types";
import type { View } from "@/lib/useLocal";
import { count, plural } from "@/lib/format";

const EASE = [0.22, 1, 0.36, 1] as const;

interface Props {
  draft: string;
  setDraft: (v: string) => void;
  commit: () => void;
  committed: string;
  data: SearchResponse | null;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  loadMore: () => void;
  filters: SearchFilters;
  filterCount: number;
  onToggleFilter: (key: keyof SearchFilters, value: string) => void;
  onRange: (after: string | undefined, before: string | undefined) => void;
  onAttachments: (v: boolean | undefined) => void;
  onClearFilters: () => void;
  /** Cross-encoder reranking, exposed because it is a request flag on /search. */
  rerank: boolean;
  onRerank: (v: boolean) => void;
  lens: Lens;
  onLens: (l: Lens) => void;
  open: EmailHit | null;
  onOpen: (h: EmailHit | null) => void;
  isSaved: (id: string) => boolean;
  onToggleSave: (h: EmailHit) => void;
  /** The sidebar is hidden below lg, so its destinations move into the header. */
  view: View;
  onView: (v: View) => void;
  savedCount: number;
}

export function Workspace(p: Props) {
  const { data } = p;

  const lenses: LensCount[] = data
    ? [
        { id: "emails", label: "Emails", n: data.total },
        { id: "people", label: "People", n: data.facets.senders.length },
        { id: "dates", label: "Dates", n: data.facets.date_histogram.filter((b) => b.doc_count > 0).length },
        {
          id: "topics",
          label: data.facets.topics.length ? "Topics" : "Folders",
          n: (data.facets.topics.length ? data.facets.topics : data.facets.folders).length,
        },
        { id: "attachments", label: "Attachments", n: data.facets.attachments.with },
      ]
    : [];

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-[var(--color-rule)] bg-[color-mix(in_srgb,var(--color-app)_90%,transparent)] px-5 py-3 backdrop-blur-md">
        <motion.div layoutId="search-pill" className="mx-auto w-full max-w-xl">
          <SearchPill
            value={p.draft}
            onChange={p.setDraft}
            onSubmit={p.commit}
            docked
            busy={p.loading}
            placeholder="Search emails"
          />
        </motion.div>

        <div className="flex shrink-0 items-center gap-2">
          <ThemeToggle />
          <span
            className="grid size-8 place-items-center rounded-full bg-[var(--color-dark)] text-[0.8125rem] font-semibold text-surface"
            title="Signed in as the local operator"
          >
            M
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-5 py-6 sm:px-7">
        {/* The sidebar is hidden below lg, so its destinations live here. */}
        <nav className="mb-4 flex items-center gap-0.5 lg:hidden">
          {(
            [
              ["search", "Search"],
              ["saved", "Saved"],
              ["history", "History"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              onClick={() => p.onView(id)}
              aria-current={p.view === id ? "page" : undefined}
              className={[
                "rounded-full px-3 py-1 text-[0.8125rem] transition-colors",
                p.view === id
                  ? "bg-[var(--color-sunk)] font-semibold"
                  : "text-[var(--color-muted)]",
              ].join(" ")}
            >
              {label}
              {id === "saved" && p.savedCount > 0 && (
                <span className="num ml-1 opacity-60">{p.savedCount}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <p className="meta">
              {/* The count crossfades instead of snapping, so a facet click
                  reads as the same number changing rather than a new page. */}
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={data ? data.total : "searching"}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                  className="inline-block"
                >
                  {data ? `${plural(data.total, "result")} for` : "Searching"}
                </motion.span>
              </AnimatePresence>
            </p>
            <h1 className="mt-0.5 font-serif text-[clamp(1.5rem,1.1rem+1.4vw,2.2rem)] leading-tight tracking-[-0.02em]">
              <span className="text-[var(--color-faint)]">&ldquo;</span>
              {p.committed || p.draft}
              <span className="text-[var(--color-faint)]">&rdquo;</span>
            </h1>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <RerankToggle on={p.rerank} onChange={p.onRerank} />
            {data && <TimingNote timing={data.timing} />}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          {data && <Tabs lenses={lenses} active={p.lens} onChange={p.onLens} />}
          {p.filterCount > 0 && (
            <button
              onClick={p.onClearFilters}
              className="meta rounded-full border border-[var(--color-rule)] px-3 py-1 transition-colors hover:border-[var(--color-rule-strong)] hover:text-[var(--color-ink)]"
            >
              Clear {plural(p.filterCount, "filter")}
            </button>
          )}
        </div>

        {p.error && (
          <div className="card mt-5 px-5 py-6">
            <p className="font-medium">Search did not run</p>
            <p className="meta mt-1">{p.error}</p>
          </div>
        )}

        {!p.error && (
          <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1.15fr)_286px]">
            <section className="min-w-0">
              {p.loading && !data ? (
                <Skeleton />
              ) : !data ? null : p.lens === "emails" ? (
                data.hits.length === 0 ? (
                  <Empty query={p.committed} hasFilters={p.filterCount > 0} onClear={p.onClearFilters} />
                ) : (
                  <>
                    <ResultList
                      hits={data.hits}
                      activeId={p.open?.id ?? null}
                      onOpen={p.onOpen}
                      isSaved={p.isSaved}
                      onToggleSave={p.onToggleSave}
                    />
                    {data.next_page_token && (
                      <div className="mt-4 flex justify-center">
                        <motion.button
                          onClick={p.loadMore}
                          disabled={p.loadingMore}
                          whileHover={p.loadingMore ? undefined : { y: -1 }}
                          whileTap={p.loadingMore ? undefined : { scale: 0.97 }}
                          transition={{ duration: 0.15, ease: [0.22, 1, 0.36, 1] }}
                          className="flex items-center gap-2 rounded-full border border-[var(--color-rule)] bg-[var(--color-surface)] px-5 py-2 text-[0.875rem] font-medium transition-colors hover:border-[var(--color-rule-strong)] disabled:opacity-60"
                        >
                          {p.loadingMore && <Spinner />}
                          {p.loadingMore ? "Loading" : "Show more results"}
                        </motion.button>
                      </div>
                    )}
                  </>
                )
              ) : p.lens === "people" ? (
                <PeopleLens facets={data.facets} filters={p.filters} onToggle={p.onToggleFilter} />
              ) : p.lens === "dates" ? (
                <DatesLens facets={data.facets} onRange={p.onRange} />
              ) : p.lens === "topics" ? (
                <TopicsLens facets={data.facets} filters={p.filters} onToggle={p.onToggleFilter} />
              ) : (
                <AttachmentsLens hits={data.hits} onOpen={p.onOpen} />
              )}
            </section>

            {/* Reading pane: a column at lg and up, an overlay below. */}
            <section className="hidden min-w-0 lg:block">
              <div className="sticky top-[84px] max-h-[calc(100dvh-108px)]">
                <ReadingPane
                  hit={p.open}
                  onClose={() => p.onOpen(null)}
                  saved={p.open ? p.isSaved(p.open.id) : false}
                  onToggleSave={() => p.open && p.onToggleSave(p.open)}
                />
              </div>
            </section>

            <aside className="hidden min-w-0 xl:block">
              {data && (
                <div className="sticky top-[84px]">
                  <Insights
                    facets={data.facets}
                    filters={p.filters}
                    total={data.total}
                    onToggle={p.onToggleFilter}
                    onRange={p.onRange}
                    onAttachments={p.onAttachments}
                  />
                </div>
              )}
            </aside>
          </div>
        )}
      </main>

      {/* Below lg the pane slides in over the list. */}
      <AnimatePresence>
        {p.open && (
          <div className="lg:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => p.onOpen(null)}
              className="fixed inset-0 z-40 bg-[rgb(27_27_25/0.2)]"
              aria-hidden
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 40, mass: 0.9 }}
              className="fixed inset-y-0 right-0 z-50 w-full max-w-[520px] p-3"
            >
              <ReadingPane
                hit={p.open}
                onClose={() => p.onOpen(null)}
                saved={p.isSaved(p.open.id)}
                onToggleSave={() => p.open && p.onToggleSave(p.open)}
              />
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="card overflow-hidden" aria-label="Loading results">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="result flex gap-3 px-4 py-3.5">
          <div className="shimmer size-[34px] shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="shimmer h-3 w-1/3" />
            <div className="shimmer h-3.5" style={{ width: `${70 - i * 4}%` }} />
            <div className="shimmer h-3" style={{ width: `${88 - i * 5}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Empty({
  query,
  hasFilters,
  onClear,
}: {
  query: string;
  hasFilters: boolean;
  onClear: () => void;
}) {
  return (
    <div className="card px-6 py-14 text-center">
      <p className="font-serif text-[1.25rem]">No emails match this search</p>
      <p className="meta mx-auto mt-2 max-w-[44ch]">
        {hasFilters
          ? "The filters may be too narrow. Clearing them searches the whole corpus again."
          : `Nothing in the index matches ${query.trim()}. Try fewer words, or drop a field like from: to widen it.`}
      </p>
      {hasFilters && (
        <button
          onClick={onClear}
          className="mt-4 rounded-full border border-[var(--color-rule)] bg-[var(--color-surface)] px-4 py-1.5 text-[0.875rem] font-medium transition-colors hover:border-[var(--color-rule-strong)]"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

export { count };

/**
 * Turns on the cross-encoder pass.
 *
 * It is a flag on /search rather than the default because it costs 100-200ms
 * and, measured against the judged query set, it trades top-10 ordering for a
 * better first hit (DECISIONS D25). The API skips it when the query carries an
 * explicit precision signal, so the label says so rather than promising a
 * change that will not happen.
 */
function RerankToggle({
  on,
  onChange,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!on)}
      aria-pressed={on}
      title="Re-score the top 50 results with a local cross-encoder. Adds 100-200ms, and is skipped for quoted phrases and field operators."
      style={on ? { color: "var(--color-surface)" } : undefined}
      className={[
        "meta flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 transition-colors",
        on
          ? "border-[var(--color-ink)] bg-[var(--color-ink)]"
          : "border-[var(--color-rule)] hover:border-[var(--color-rule-strong)] hover:text-[var(--color-ink)]",
      ].join(" ")}
    >
      <span
        className="size-1.5 rounded-full"
        style={{ background: on ? "#c08a2e" : "var(--color-faint)" }}
        aria-hidden
      />
      Rerank
    </button>
  );
}

/** A one-element spinner. Sized to sit on a text baseline without shifting it. */
function Spinner() {
  return (
    <span
      className="inline-block size-3.5 shrink-0 animate-spin rounded-full border-[1.5px] border-[var(--color-rule-strong)] border-t-[var(--color-ink)]"
      aria-hidden
    />
  );
}
