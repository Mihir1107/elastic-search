"use client";

/**
 * The result list.
 *
 * A row has to answer two questions at a glance: what is this, and why did it
 * come back. Sender, subject and date answer the first; the marker ink and the
 * two-bar signal answer the second.
 */

import type React from "react";
import { motion } from "motion/react";
import type { EmailHit } from "@/lib/types";
import { personName, shortDate } from "@/lib/format";
import { Marker } from "./Marker";
import { SignalBar } from "./SignalBar";
import { Avatar } from "./Avatar";

interface Props {
  hits: EmailHit[];
  activeId: string | null;
  onOpen: (hit: EmailHit) => void;
  isSaved: (id: string) => boolean;
  onToggleSave: (hit: EmailHit) => void;
  /** Review tags for a hit, including changes made since it was fetched. */
  tagsFor: (hit: EmailHit) => string[];
}

export function ResultList({ hits, activeId, onOpen, isSaved, onToggleSave, tagsFor }: Props) {
  return (
    // ink-sweep: each match's marker stroke is drawn in as its row arrives.
    <div className="card ink-sweep overflow-hidden">
      {hits.map((hit, i) => (
        <Row
          key={hit.id}
          hit={hit}
          index={i}
          active={activeId === hit.id}
          onOpen={onOpen}
          saved={isSaved(hit.id)}
          onToggleSave={onToggleSave}
          reviewTags={tagsFor(hit)}
        />
      ))}
    </div>
  );
}

function Row({
  hit,
  index,
  active,
  onOpen,
  saved,
  onToggleSave,
  reviewTags,
}: {
  hit: EmailHit;
  index: number;
  active: boolean;
  onOpen: (h: EmailHit) => void;
  saved: boolean;
  onToggleSave: (h: EmailHit) => void;
  reviewTags: string[];
}) {
  const bodyFragment = hit.highlight.body?.[0];
  const semanticOnly = hit.signals.bm25_rank === null && hit.signals.vector_rank !== null;
  const snippet = bodyFragment ?? hit.semantic_snippet;
  const tags = hit.topics.length ? hit.topics : hit.folder ? [hit.folder] : [];
  const stagger = Math.min(index, 8) * 22;

  return (
    <motion.article
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.26,
        ease: [0.22, 1, 0.36, 1],
        // Stagger only the first screenful; later rows would feel sluggish.
        delay: stagger / 1000,
      }}
      // The row settles first, then its ink is drawn.
      style={{ "--mk-delay": `${stagger + 140}ms` } as React.CSSProperties}
      className="result cursor-pointer px-4 py-3.5"
      data-active={active}
      // A clickable row needs to be reachable and operable without a mouse.
      role="button"
      tabIndex={0}
      aria-current={active ? "true" : undefined}
      aria-label={`${hit.from_name || personName(hit.from)}: ${hit.subject}`}
      onClick={() => onOpen(hit)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(hit);
        }
      }}
    >
      {active && (
        <motion.span
          layoutId="result-rail"
          className="result-rail"
          transition={{ type: "spring", stiffness: 520, damping: 42 }}
          aria-hidden
        />
      )}
      <div className="flex gap-3">
        <Avatar address={hit.from} name={hit.from_name} />

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <span className="truncate text-[0.875rem] font-medium">
              {hit.from_name || personName(hit.from)}
            </span>
            <time className="meta num shrink-0 text-[0.75rem]" dateTime={hit.date}>
              {shortDate(hit.date)}
            </time>
          </div>

          <h3 className="subject mt-0.5 truncate">
            {hit.highlight.subject?.[0] ? (
              <Marker fragment={hit.highlight.subject[0]} />
            ) : (
              hit.subject
            )}
          </h3>

          {snippet && (
            <p className="line-clamp-2 mt-1 text-[0.8125rem] leading-relaxed text-[var(--color-muted)]">
              {bodyFragment ? (
                <Marker fragment={bodyFragment} />
              ) : (
                <mark className="mk mk-sem mk-block">{snippet}</mark>
              )}
            </p>
          )}

          <div className="mt-2 flex items-center gap-2">
            {/* Tags give up room before the controls do, so the star is never
                pushed off the edge on a densely tagged result. */}
            <span className="flex min-w-0 flex-1 gap-1.5 overflow-hidden">
              {/* The reviewer's marks come first: they are the point of a review. */}
              {reviewTags.map((t) => (
                <span key={`review-${t}`} className="tag tag-review">
                  {t}
                </span>
              ))}
              {tags.slice(0, 3).map((t) => (
                <span key={t} className="tag">
                  {t}
                </span>
              ))}
            </span>

            <span className="flex shrink-0 items-center gap-2.5">
              {semanticOnly && (
                <span
                  title="Matched on meaning, not on the words you typed"
                  className="size-1.5 rounded-full"
                  style={{ background: "var(--color-marker-sem-solid)" }}
                />
              )}
              {hit.has_attachment && <Clip />}
              <SignalBar signals={hit.signals} delay={stagger} />
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleSave(hit);
                }}
                aria-pressed={saved}
                aria-label={saved ? "Remove from saved" : "Save this email"}
                className="text-[var(--color-faint)] transition-colors hover:text-[var(--color-ink)]"
              >
                <Star filled={saved} />
              </button>
            </span>
          </div>
        </div>
      </div>
    </motion.article>
  );
}

function Star({ filled }: { filled: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 1.9l1.85 3.75 4.15.6-3 2.93.71 4.12L8 11.35l-3.71 1.95.71-4.12-3-2.93 4.15-.6L8 1.9z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
        fill={filled ? "var(--color-marker-key-solid)" : "none"}
        style={filled ? { color: "var(--color-marker-key-solid)" } : undefined}
      />
    </svg>
  );
}

function Clip() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      className="text-[var(--color-faint)]"
      aria-label="Has an attachment"
      role="img"
    >
      <path
        d="M8.5 3.2L4.4 7.3a1.6 1.6 0 002.3 2.3l4.1-4.1a3 3 0 00-4.2-4.2L2.3 5.5a4.3 4.3 0 006.1 6.1"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
        transform="translate(-0.5 -0.6)"
      />
    </svg>
  );
}
