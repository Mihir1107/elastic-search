"use client";

/**
 * Debounced search-as-you-type with cancellation.
 *
 * Every keystroke supersedes the last request, so the in-flight one is aborted
 * rather than left to land out of order — without that, a fast typist sees
 * results flicker backwards. A sequence number guards the same race for
 * responses that resolve after an abort slips through.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { search as runSearch } from "./api";
import type { SearchFilters, SearchParams, SearchResponse } from "./types";

const DEBOUNCE_MS = 140;

interface State {
  data: SearchResponse | null;
  loading: boolean;
  error: string | null;
  loadingMore: boolean;
}

export function useSearch(
  query: string,
  filters: SearchFilters,
  rerank: boolean,
  enabled: boolean,
) {
  const [state, setState] = useState<State>({
    data: null,
    loading: false,
    error: null,
    loadingMore: false,
  });

  const seq = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const key = JSON.stringify({ query, filters, rerank });

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null, loadingMore: false });
      return;
    }

    const id = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));

    const timer = setTimeout(() => {
      abort.current?.abort();
      const ac = new AbortController();
      abort.current = ac;

      runSearch({ q: query, filters, rerank }, ac.signal)
        .then((data) => {
          if (id !== seq.current) return;
          setState({ data, loading: false, error: null, loadingMore: false });
        })
        .catch((e: unknown) => {
          if (id !== seq.current) return;
          if (e instanceof Error && e.name === "AbortError") return;
          setState({
            data: null,
            loading: false,
            loadingMore: false,
            error: e instanceof Error ? e.message : "Search failed",
          });
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
    // `key` captures every input; query/filters/rerank are read inside.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  /** Appends the next page, keeping the rows already on screen. */
  const loadMore = useCallback(async () => {
    const token = state.data?.next_page_token;
    if (!token || state.loadingMore) return;

    setState((s) => ({ ...s, loadingMore: true }));
    const params: SearchParams = { q: query, filters, rerank, page_token: token };

    try {
      const next = await runSearch(params);
      setState((s) =>
        s.data
          ? {
              ...s,
              loadingMore: false,
              data: {
                ...next,
                hits: [...s.data.hits, ...next.hits],
                // Keep the first page's timing; it describes the search itself.
                timing: s.data.timing,
              },
            }
          : { ...s, loadingMore: false },
      );
    } catch (e) {
      setState((s) => ({
        ...s,
        loadingMore: false,
        error: e instanceof Error ? e.message : "Could not load more results",
      }));
    }
  }, [query, filters, rerank, state.data?.next_page_token, state.loadingMore]);

  return { ...state, loadMore };
}
