"use client";

/**
 * The entry screen.
 *
 * Everything on it points at one control. When the field takes focus the hero
 * copy recedes and a hint row takes its place — the page gets out of the way as
 * soon as the person starts writing, which is the whole interaction.
 */

import { AnimatePresence, motion } from "motion/react";
import { SearchPill } from "./SearchPill";
import { Collage } from "./Collage";
import { TopBar } from "./TopBar";
import { count } from "@/lib/format";
import type { Health } from "@/lib/types";

/**
 * Each starter demonstrates a different retrieval path against the indexed
 * mailboxes, and each returns real results — an example that comes back empty
 * teaches the wrong thing on first contact.
 */
const STARTERS = [
  // Hybrid free text: BM25 and the vector leg both contribute.
  { label: "California power crisis", q: "california power crisis" },
  // Field operators plus a date window, resolved by the query parser.
  {
    label: "Arnold on gas, Q3 2001",
    q: "from:john.arnold@enron.com gas after:2001-07-01 before:2001-09-30",
  },
  // A quoted phrase, matched exactly on the .exact subfields.
  { label: "\u201CRolling blackouts\u201D", q: '"rolling blackouts"' },
  // No shared keywords with its best answers: this one is the vector leg's job.
  { label: "Who worried about losses?", q: "concerns about hiding financial losses" },
];

const EASE = [0.22, 1, 0.36, 1] as const;

interface Props {
  draft: string;
  setDraft: (v: string) => void;
  commit: () => void;
  loading: boolean;
  typing: boolean;
  onTypingChange: (v: boolean) => void;
  onStarter: (q: string) => void;
  /** True once a query is committed: the hero blurs away as the bar departs. */
  leaving: boolean;
  /** Drives the corpus size in the hero, so the claim matches the live index. */
  health: Health | null;
}

export function Landing({
  draft,
  setDraft,
  commit,
  loading,
  typing,
  onTypingChange,
  onStarter,
  leaving,
  health,
}: Props) {
  // The hero recedes while typing and clears entirely on commit.
  const receded = typing || draft.length > 0;

  return (
    <div className="relative min-h-dvh bg-[var(--color-paper)]">
      <Collage />

      <div className="relative flex min-h-dvh flex-col">
        <TopBar />

        <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-5 pb-16">
          <motion.div
            animate={{
              opacity: leaving ? 0 : receded ? 0.45 : 1,
              filter: leaving ? "blur(6px)" : "blur(0px)",
              y: leaving ? -12 : 0,
            }}
            transition={{ duration: 0.4, ease: EASE }}
            className="text-center"
          >
            <p className="eyebrow">Search &middot; Understand &middot; Discover</p>
            <h1 className="display mt-5 text-balance">
              Every email, one question at a time.
            </h1>
            <p className="mx-auto mt-5 max-w-[46ch] text-[1.0625rem] leading-relaxed text-[var(--color-muted)]">
              {health?.docs
                ? `Search ${count(health.docs)} indexed emails for people, ideas, dates and decisions.`
                : "Search your archive for people, ideas, dates and decisions."}{" "}
              Ask naturally. Get precise answers.
            </p>
          </motion.div>

          {/* layoutId hands this pill to the results header on commit. */}
          <motion.div layoutId="search-pill" className="mt-9">
            <SearchPill
              value={draft}
              onChange={setDraft}
              onSubmit={commit}
              docked={false}
              busy={loading}
              onFocusChange={onTypingChange}
            />
          </motion.div>

          <div className="relative mt-6 min-h-[86px]">
            <AnimatePresence mode="wait" initial={false}>
              {receded ? (
                <motion.div
                  key="hints"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: leaving ? 0 : 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.22, ease: EASE }}
                  className="text-center"
                >
                  <p className="meta flex flex-wrap items-center justify-center gap-x-7 gap-y-2">
                    <Hint keys={["Enter"]}>to search</Hint>
                    <Hint keys={["Tab"]}>to add a filter</Hint>
                    <Hint keys={["⌘", "K"]}>for shortcuts</Hint>
                  </p>
                  <p className="mt-7 font-serif text-[1.0625rem] italic text-[var(--color-faint)]">
                    A little context today. A lot of clarity tomorrow.
                  </p>
                </motion.div>
              ) : (
                <motion.div
                  key="starters"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.22, ease: EASE }}
                  className="text-center"
                >
                  <p className="eyebrow">Try searching</p>
                  <div className="mt-3.5 flex flex-wrap justify-center gap-2">
                    {STARTERS.map((s) => (
                      <button
                        key={s.q}
                        onClick={() => onStarter(s.q)}
                        className="rounded-full border border-[var(--color-rule)] bg-[var(--color-surface)] px-3.5 py-1.5 text-[0.8125rem] text-[var(--color-muted)] shadow-[var(--shadow-card)] transition-all hover:-translate-y-px hover:border-[var(--color-rule-strong)] hover:text-[var(--color-ink)]"
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </main>

        <motion.footer
          animate={{ opacity: leaving ? 0 : receded ? 0.4 : 1 }}
          transition={{ duration: 0.3, ease: EASE }}
          className="relative pb-9 text-center"
        >
          <div className="mx-auto flex max-w-xl items-center gap-4 px-5">
            {/* The rules only earn their place when the line fits on one row. */}
            <span className="hidden h-px flex-1 bg-[var(--color-rule)] sm:block" />
            <span className="eyebrow text-center sm:whitespace-nowrap">
              Good decisions build on good information
            </span>
            <span className="hidden h-px flex-1 bg-[var(--color-rule)] sm:block" />
          </div>
        </motion.footer>
      </div>
    </div>
  );
}

function Hint({ keys, children }: { keys: string[]; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-flex gap-1">
        {keys.map((k) => (
          <kbd
            key={k}
            className="min-w-[1.4rem] rounded border border-[var(--color-rule)] bg-[var(--color-surface)] px-1.5 py-0.5 text-center font-sans text-[0.6875rem] font-semibold text-[var(--color-muted)]"
          >
            {k}
          </kbd>
        ))}
      </span>
      {children}
    </span>
  );
}
