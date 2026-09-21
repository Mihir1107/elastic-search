"use client";

/**
 * Review actions for the result set: tag everything on screen, export the set.
 *
 * Export is a plain download link. The API decides what "the set" is (the full
 * filtered set, or the ranked list for a text query) and says so in the file's
 * response headers; see api/app/routes/export.py.
 */

import { useEffect, useRef, useState } from "react";
import { PRESET_TAGS } from "@/lib/useTags";

export function ReviewActions({
  count,
  onTagAll,
  exportHref,
  error,
}: {
  /** How many results are on screen, i.e. what "Tag page" will touch. */
  count: number;
  onTagAll: (tag: string) => void;
  /** Null in fixture mode, where there is no API to export from. */
  exportHref: string | null;
  error: string | null;
}) {
  const [menu, setMenu] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) {
        setMenu(false);
      }
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [menu]);

  const button =
    "meta shrink-0 rounded-full border border-[var(--color-rule)] px-3 py-1 transition-colors hover:border-[var(--color-rule-strong)] hover:text-[var(--color-ink)]";

  return (
    <div ref={ref} className="relative flex shrink-0 items-center gap-2">
      {error && (
        <span className="meta max-w-[18ch] truncate text-[var(--color-ink)]" title={error} role="status">
          Tag not saved
        </span>
      )}
      <button
        onClick={() => setMenu((m) => !m)}
        aria-expanded={menu}
        aria-haspopup="menu"
        disabled={count === 0}
        className={`${button} disabled:opacity-50`}
      >
        Tag page
      </button>
      {menu && (
        <div
          role="menu"
          className="card absolute right-0 top-full z-40 mt-1.5 w-52 p-1.5 shadow-[0_12px_32px_-12px_rgb(27_27_25/0.3)]"
        >
          <p className="meta px-2 pb-1 pt-0.5 text-[0.75rem]">
            Tag all {count} results on screen as
          </p>
          {PRESET_TAGS.map((t) => (
            <button
              key={t}
              role="menuitem"
              onClick={() => {
                onTagAll(t);
                setMenu(false);
              }}
              className="w-full rounded-md px-2 py-1.5 text-left text-[0.875rem] capitalize transition-colors hover:bg-[var(--color-sunk)]"
            >
              {t}
            </button>
          ))}
        </div>
      )}
      {exportHref && (
        <a
          href={exportHref}
          download
          className={button}
          title="Download these results as CSV: every match for a filter-only search, the ranked list for a text search"
        >
          Export CSV
        </a>
      )}
    </div>
  );
}
