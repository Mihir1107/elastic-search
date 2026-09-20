"use client";

/**
 * Ledger.
 *
 * Two states, one page. The entry screen puts everything behind one field;
 * committing a query hands that same field to the results header — the pill is
 * a single element with a shared layoutId, so it travels rather than being
 * replaced, while the hero blurs away behind it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LayoutGroup } from "motion/react";
import { Landing } from "@/components/Landing";
import { Workspace } from "@/components/Workspace";
import { Sidebar } from "@/components/Sidebar";
import { CollectionsView, HistoryView, SavedView } from "@/components/Library";
import type { Lens } from "@/components/Tabs";
import { useSearch } from "@/lib/useSearch";
import { useHistory, useSaved, type View } from "@/lib/useLocal";
import { compactFilters, countFilters, isEmpty } from "@/lib/query";
import { getEmail, getHealth } from "@/lib/api";
import type { EmailHit, Health, SearchFilters } from "@/lib/types";

export default function Page() {
  const [draft, setDraft] = useState("");
  const [committed, setCommitted] = useState("");
  const [facetFilters, setFacetFilters] = useState<SearchFilters>({});
  const [open, setOpen] = useState<EmailHit | null>(null);
  const [lens, setLens] = useState<Lens>("emails");
  const [view, setView] = useState<View>("search");
  const [typing, setTyping] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);

  const { saved, toggle: toggleSave, isSaved } = useSaved();
  const { history, record, clear: clearHistory } = useHistory();

  const searching = committed.length > 0 || countFilters(facetFilters) > 0;
  const filters = useMemo(() => compactFilters(facetFilters), [facetFilters]);

  // Typing searches live; the committed query is what opens the workspace.
  const active = searching ? draft || committed : "";

  const { data, loading, error, loadingMore, loadMore } = useSearch(
    active,
    filters,
    false,
    searching,
  );

  useEffect(() => {
    const ac = new AbortController();
    getHealth(ac.signal)
      .then(setHealth)
      .catch(() => undefined);
    return () => ac.abort();
  }, []);

  // Record a search once its result count is known.
  useEffect(() => {
    if (committed && data && !loading) record(committed, data.total);
  }, [committed, data, loading, record]);

  /** Blur the hero, then swap. HERO_EXIT_MS matches the Landing transition. */
  const HERO_EXIT_MS = 260;
  const exitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (exitTimer.current) clearTimeout(exitTimer.current);
  }, []);

  const start = useCallback((q: string) => {
    setLeaving(true);
    if (exitTimer.current) clearTimeout(exitTimer.current);
    exitTimer.current = setTimeout(() => {
      setCommitted(q);
      setView("search");
      setLens("emails");
    }, HERO_EXIT_MS);
  }, []);

  const commit = useCallback(() => {
    if (isEmpty(draft) && countFilters(facetFilters) === 0) return;
    // Already in the workspace: no hero to clear, so switch immediately.
    if (searching) {
      setCommitted(draft);
      setView("search");
      return;
    }
    start(draft);
  }, [draft, facetFilters, searching, start]);

  const runQuery = useCallback(
    (q: string) => {
      setDraft(q);
      if (searching) {
        setCommitted(q);
        setView("search");
        setLens("emails");
        return;
      }
      start(q);
    },
    [searching, start],
  );

  const toggleFilter = useCallback((key: keyof SearchFilters, value: string) => {
    setFacetFilters((f) => {
      const current = (f[key] as string[] | undefined) ?? [];
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      return { ...f, [key]: next.length ? next : undefined };
    });
  }, []);

  const reset = useCallback(() => {
    setDraft("");
    setCommitted("");
    setFacetFilters({});
    setOpen(null);
    setLens("emails");
    setView("search");
    setLeaving(false);
    setTyping(false);
  }, []);

  /** Opening a saved email needs the full doc; fetch it, then show the pane. */
  const openById = useCallback(async (id: string) => {
    try {
      const doc = await getEmail(id);
      setView("search");
      setOpen(doc);
    } catch {
      // The email is no longer in the index; leave the saved entry alone.
    }
  }, []);

  const filterCount = countFilters(filters);
  const showWorkspace = searching && view === "search";

  const changeView = useCallback((next: View) => {
    setOpen(null);
    setView(next);
  }, []);

  return (
    /* LayoutGroup is what lets the pill travel: Landing and Workspace each
       render one element with layoutId="search-pill", and because the swap is
       synchronous, motion interpolates between their two positions. There is
       deliberately no AnimatePresence here — an exiting Workspace never
       finishes leaving while its rows, reading pane and shared-layout pill are
       all still animating, which left both views on screen at once. */
    <LayoutGroup>
      <div className="flex min-h-dvh">
        {searching && (
          <Sidebar
            view={view}
            onView={changeView}
            savedCount={saved.length}
            health={health}
            onHome={reset}
          />
        )}

        <div className="min-w-0 flex-1">
          {!searching ? (
            <Landing
              draft={draft}
              setDraft={setDraft}
              commit={commit}
              loading={loading}
              typing={typing}
              onTypingChange={setTyping}
              onStarter={runQuery}
              leaving={leaving}
              health={health}
            />
          ) : showWorkspace ? (
            <Workspace
              draft={draft}
              setDraft={setDraft}
              commit={commit}
              committed={committed}
              data={data}
              loading={loading}
              loadingMore={loadingMore}
              error={error}
              loadMore={loadMore}
              filters={filters}
              filterCount={filterCount}
              onToggleFilter={toggleFilter}
              onRange={(after, before) =>
                setFacetFilters((f) => ({ ...f, after, before }))
              }
              onAttachments={(v) =>
                setFacetFilters((f) => ({ ...f, has_attachment: v }))
              }
              onClearFilters={() => setFacetFilters({})}
              lens={lens}
              onLens={setLens}
              open={open}
              onOpen={setOpen}
              isSaved={isSaved}
              onToggleSave={toggleSave}
              view={view}
              onView={changeView}
              savedCount={saved.length}
            />
          ) : view === "saved" ? (
            <SavedView
              saved={saved}
              onOpen={openById}
              onRemove={(id) => {
                const entry = saved.find((s) => s.id === id);
                if (entry) toggleSave({ ...entry } as unknown as EmailHit);
              }}
            />
          ) : view === "history" ? (
            <HistoryView history={history} onRun={runQuery} onClear={clearHistory} />
          ) : (
            <CollectionsView />
          )}
        </div>
      </div>
    </LayoutGroup>
  );
}
