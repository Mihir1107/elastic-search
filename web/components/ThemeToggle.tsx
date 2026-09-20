"use client";

/** Light/dark switch. The choice is remembered; the boot script in layout.tsx
 *  applies it before first paint so the page never flashes the wrong theme. */

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.theme = next ? "dark" : "light";
    try {
      localStorage.setItem("ledger-theme", next ? "dark" : "light");
    } catch {
      // Private browsing: the theme simply does not persist.
    }
  }

  return (
    <button
      onClick={toggle}
      className="grid size-8 place-items-center rounded-full text-[var(--color-muted)] transition-colors hover:bg-[var(--color-sunk)] hover:text-[var(--color-ink)]"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      aria-pressed={dark}
    >
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 18 18" fill="none" aria-hidden>
          <path
            d="M15 11.2A6.6 6.6 0 016.8 3 6.6 6.6 0 1015 11.2z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden>
          <circle cx="9" cy="9" r="3.3" stroke="currentColor" strokeWidth="1.5" />
          <g stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M9 1.6v1.8M9 14.6v1.8M16.4 9h-1.8M3.4 9H1.6" />
            <path d="M14.2 3.8l-1.3 1.3M5.1 12.9l-1.3 1.3M14.2 14.2l-1.3-1.3M5.1 5.1L3.8 3.8" />
          </g>
        </svg>
      )}
    </button>
  );
}
