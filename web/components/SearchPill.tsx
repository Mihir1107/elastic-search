"use client";

/**
 * The search field.
 *
 * One box does everything, so the box explains itself: a mirror layer under the
 * transparent input paints each token in the colour of what the parser made of
 * it — a person, a phrase, a date bound, or plain text. Nobody picks "fuzzy" or
 * "prefix" from a dropdown, so the field shows what was decided instead.
 *
 * The mirror and the input must have identical text metrics or the chips drift
 * off the glyphs, which is why chips are painted with background + box-shadow
 * and never padding. See `.field-stack` in globals.css.
 */

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { tokenize } from "@/lib/query";
import type { QueryToken, Suggestion } from "@/lib/types";
import { suggest } from "@/lib/api";

function chipClass(t: QueryToken): string {
  switch (t.kind) {
    case "person":
      return "tok tok-person";
    case "phrase":
      return "tok tok-phrase";
    case "date":
      return "tok tok-date";
    case "unknown":
      return "tok-unknown";
    default:
      return "";
  }
}

/** Rebuilds the raw string as spans, preserving exact inter-token spacing. */
function Mirror({ value, ref }: { value: string; ref: React.Ref<HTMLDivElement> }) {
  const tokens = useMemo(() => tokenize(value), [value]);
  const parts: React.ReactNode[] = [];
  let cursor = 0;

  tokens.forEach((t, i) => {
    if (t.start > cursor) parts.push(value.slice(cursor, t.start));
    const cls = chipClass(t);
    parts.push(
      cls ? (
        <span key={`t${i}`} className={cls}>
          {t.raw}
        </span>
      ) : (
        t.raw
      ),
    );
    cursor = t.end;
  });
  if (cursor < value.length) parts.push(value.slice(cursor));

  return (
    <div ref={ref} className="field-mirror" aria-hidden>
      {parts}
    </div>
  );
}

interface Props {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  /** Compact version for the results header. */
  docked: boolean;
  busy: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  onFocusChange?: (focused: boolean) => void;
}

export function SearchPill({
  value,
  onChange,
  onSubmit,
  docked,
  busy,
  placeholder = "Ask anything about your emails...",
  autoFocus = false,
  onFocusChange,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const [focused, setFocused] = useState(false);
  const [hints, setHints] = useState<Suggestion[]>([]);
  const [hintIndex, setHintIndex] = useState(-1);
  const listId = useId();

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  // ⌘K / Ctrl+K focuses the field from anywhere, as the hint row promises.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Autocomplete the last word, but never inside a quoted phrase.
  useEffect(() => {
    const tail = value.split(/\s+/).pop() ?? "";
    const operand = tail.replace(/^(from|to|cc|subject):/i, "");
    const quoted = (value.match(/"/g)?.length ?? 0) % 2 === 1;

    if (quoted || operand.length < 2) {
      setHints([]);
      setHintIndex(-1);
      return;
    }

    const ac = new AbortController();
    const t = setTimeout(() => {
      suggest(operand, ac.signal)
        .then((s) => {
          setHints(s);
          setHintIndex(-1);
        })
        .catch(() => undefined);
    }, 110);

    return () => {
      ac.abort();
      clearTimeout(t);
    };
  }, [value]);

  function syncScroll() {
    if (mirrorRef.current && inputRef.current) {
      mirrorRef.current.scrollLeft = inputRef.current.scrollLeft;
    }
  }

  function setFocus(next: boolean) {
    setFocused(next);
    onFocusChange?.(next);
  }

  function applyHint(s: Suggestion) {
    const words = value.split(/(\s+)/);
    for (let i = words.length - 1; i >= 0; i--) {
      if (words[i].trim()) {
        const op = words[i].match(/^(from|to|cc|subject):/i);
        words[i] =
          s.kind === "person" ? `${op ? op[0] : "from:"}${s.value}` : `"${s.value}"`;
        break;
      }
    }
    onChange(`${words.join("")} `);
    setHints([]);
    inputRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (hints.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHintIndex((i) => (i + 1) % hints.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHintIndex((i) => (i <= 0 ? hints.length - 1 : i - 1));
        return;
      }
      if (e.key === "Tab" && hintIndex >= 0) {
        e.preventDefault();
        applyHint(hints[hintIndex]);
        return;
      }
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (hintIndex >= 0 && hints[hintIndex]) applyHint(hints[hintIndex]);
      else {
        setHints([]);
        onSubmit();
      }
    }
    if (e.key === "Escape") {
      setHints([]);
      inputRef.current?.blur();
    }
  }

  const showHints = focused && hints.length > 0;

  return (
    <div className="relative">
      <motion.div
        animate={{
          boxShadow: focused ? "var(--shadow-pill-lift)" : "var(--shadow-pill)",
        }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className={[
          "relative flex items-center rounded-full border bg-[var(--color-surface)]",
          "transition-colors duration-200",
          focused ? "border-[var(--color-rule-strong)]" : "border-[var(--color-rule)]",
          docked ? "gap-2.5 py-1.5 pl-4 pr-1.5" : "gap-3 py-2.5 pl-6 pr-2.5",
        ].join(" ")}
      >
        <Glyph busy={busy} />

        <div
          className="field-stack min-w-0 flex-1"
          style={{ fontSize: docked ? "0.9375rem" : "1.0625rem" }}
        >
          <Mirror value={value} ref={mirrorRef} />
          <input
            ref={inputRef}
            className="field-input"
            value={value}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            onScroll={syncScroll}
            onFocus={() => setFocus(true)}
            // Delayed so a click on a suggestion lands before the list unmounts.
            onBlur={() => setTimeout(() => setFocus(false), 140)}
            spellCheck={false}
            autoComplete="off"
            aria-label="Search emails"
            aria-expanded={showHints}
            aria-controls={listId}
            role="combobox"
            aria-autocomplete="list"
          />
        </div>

        {value && (
          <button
            onClick={() => {
              onChange("");
              inputRef.current?.focus();
            }}
            className="shrink-0 rounded-full p-1 text-[var(--color-faint)] transition-colors hover:text-[var(--color-ink)]"
            aria-label="Clear search"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        )}

        <button
          onClick={() => (value.trim() ? onSubmit() : inputRef.current?.focus())}
          className={[
            "grid shrink-0 place-items-center rounded-full bg-[var(--color-dark)]",
            "transition-all duration-200 hover:scale-[1.06] active:scale-95",
            value.trim() ? "" : "opacity-75",
            docked ? "size-8" : "size-10",
          ].join(" ")}
          aria-label="Search"
        >
          <svg
            width={docked ? 15 : 17}
            height={docked ? 15 : 17}
            viewBox="0 0 18 18"
            fill="none"
            aria-hidden
          >
            <path
              d="M3.5 9h11M10 4.5L14.5 9 10 13.5"
              stroke="var(--color-surface)"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </motion.div>

      <AnimatePresence>
        {showHints && (
          <motion.ul
            id={listId}
            role="listbox"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-x-3 top-[calc(100%+10px)] z-40 overflow-hidden rounded-xl border border-[var(--color-rule)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-pill-lift)]"
          >
            {hints.map((h, i) => (
              <li key={`${h.kind}-${h.value}`} role="option" aria-selected={i === hintIndex}>
                <button
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => applyHint(h)}
                  onMouseEnter={() => setHintIndex(i)}
                  className={[
                    "flex w-full items-center gap-3 px-4 py-2 text-left text-[0.9375rem] transition-colors",
                    i === hintIndex ? "bg-[var(--color-sunk)]" : "",
                  ].join(" ")}
                >
                  <span
                    className="size-1.5 shrink-0 rounded-full"
                    style={{
                      background:
                        h.kind === "person"
                          ? "var(--color-marker-sem-solid)"
                          : "var(--color-marker-key-solid)",
                    }}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 truncate">
                    {h.kind === "person" ? h.label : h.value}
                  </span>
                  <span className="meta shrink-0">
                    {h.kind === "person" ? `${h.doc_count} emails` : "phrase"}
                  </span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

/** The magnifier doubles as the activity indicator so nothing else moves. */
function Glyph({ busy }: { busy: boolean }) {
  return (
    <span className="relative grid size-5 shrink-0 place-items-center" aria-hidden>
      <svg width="17" height="17" viewBox="0 0 18 18" fill="none">
        <circle
          cx="8"
          cy="8"
          r="5.4"
          stroke="var(--color-muted)"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeDasharray={busy ? "8 26" : undefined}
          className={busy ? "origin-center animate-spin" : ""}
          style={busy ? { animationDuration: "0.9s" } : undefined}
        />
        <path d="M12.2 12.2L16 16" stroke="var(--color-muted)" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </span>
  );
}
