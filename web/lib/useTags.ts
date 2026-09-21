"use client";

/**
 * Review tags: what the reviewer has marked, and the counts behind the Tags facet.
 *
 * Tags are server state (the API keeps them in their own index, D37), but a
 * click has to show at once, so a change is applied locally first and rolled
 * back if the API refuses it. A search result only knows the tags it had when
 * it was fetched; `tagsFor` lays any change made since over the top.
 */

import { useCallback, useEffect, useState } from "react";
import { batchTags, listTags, setTags } from "./api";
import type { TagCount } from "./types";

/** The marks a document review starts with; any other tag name also works. */
export const PRESET_TAGS = ["relevant", "privileged", "hot"] as const;

export function useTags() {
  const [overrides, setOverrides] = useState<Record<string, string[]>>({});
  const [counts, setCounts] = useState<TagCount[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listTags()
      .then(setCounts)
      .catch(() => undefined);
  }, []);

  useEffect(refresh, [refresh]);

  const tagsFor = useCallback(
    (id: string, fetched: string[]) => overrides[id] ?? fetched,
    [overrides],
  );

  /** Replace one email's tags; `current` is what to restore if the API refuses. */
  const set = useCallback(
    async (id: string, next: string[], current: string[]) => {
      setError(null);
      setOverrides((o) => ({ ...o, [id]: next }));
      try {
        const stored = await setTags(id, next);
        setOverrides((o) => ({ ...o, [id]: stored }));
        refresh();
      } catch (e) {
        setOverrides((o) => ({ ...o, [id]: current }));
        setError(e instanceof Error ? e.message : "Could not save the tag");
      }
    },
    [refresh],
  );

  /** Add one tag to many emails at once (the "Tag page" action). */
  const tagMany = useCallback(
    async (items: { id: string; tags: string[] }[], tag: string) => {
      if (!items.length) return;
      setError(null);
      const before = Object.fromEntries(items.map((i) => [i.id, i.tags]));
      setOverrides((o) => ({
        ...o,
        ...Object.fromEntries(
          items.map((i) => [i.id, [...new Set([...i.tags, tag])].sort()]),
        ),
      }));
      try {
        await batchTags(
          items.map((i) => i.id),
          [tag],
        );
        refresh();
      } catch (e) {
        setOverrides((o) => ({ ...o, ...before }));
        setError(e instanceof Error ? e.message : "Could not tag these emails");
      }
    },
    [refresh],
  );

  return { counts, tagsFor, set, tagMany, error };
}

export type Tags = ReturnType<typeof useTags>;
