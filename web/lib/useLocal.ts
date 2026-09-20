"use client";

/**
 * Per-browser state: starred emails and recent searches.
 *
 * There are no user accounts in this build (an explicit non-goal in the
 * kickoff), so both live in localStorage. That means they are per-browser and
 * never leave the machine. Every access is wrapped because storage throws in
 * private windows and can come back empty at any time.
 */

import { useCallback, useEffect, useState } from "react";
import type { EmailHit } from "./types";

export type View = "search" | "saved" | "history" | "collections";

const SAVED_KEY = "ledger-saved";
const HISTORY_KEY = "ledger-history";
const HISTORY_MAX = 25;

export interface SavedEmail {
  id: string;
  subject: string;
  from: string;
  from_name: string;
  date: string;
  savedAt: number;
}

export interface HistoryEntry {
  q: string;
  total: number;
  at: number;
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable or full; the feature degrades to this session only.
  }
}

export function useSaved() {
  const [saved, setSaved] = useState<SavedEmail[]>([]);

  // Read after mount so the server and client render the same first pass.
  useEffect(() => {
    setSaved(read<SavedEmail[]>(SAVED_KEY, []));
  }, []);

  const toggle = useCallback((hit: EmailHit) => {
    setSaved((prev) => {
      const next = prev.some((s) => s.id === hit.id)
        ? prev.filter((s) => s.id !== hit.id)
        : [
            {
              id: hit.id,
              subject: hit.subject,
              from: hit.from,
              from_name: hit.from_name,
              date: hit.date,
              savedAt: Date.now(),
            },
            ...prev,
          ];
      write(SAVED_KEY, next);
      return next;
    });
  }, []);

  const isSaved = useCallback(
    (id: string) => saved.some((s) => s.id === id),
    [saved],
  );

  return { saved, toggle, isSaved };
}

export function useHistory() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setHistory(read<HistoryEntry[]>(HISTORY_KEY, []));
  }, []);

  const record = useCallback((q: string, total: number) => {
    const query = q.trim();
    if (!query) return;
    setHistory((prev) => {
      // Re-running a search moves it to the top rather than duplicating it.
      const next = [{ q: query, total, at: Date.now() }, ...prev.filter((h) => h.q !== query)].slice(
        0,
        HISTORY_MAX,
      );
      write(HISTORY_KEY, next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setHistory([]);
    write(HISTORY_KEY, []);
  }, []);

  return { history, record, clear };
}
