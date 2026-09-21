"use client";

/**
 * The reading pane: the selected email, and the thread it belongs to.
 *
 * Thread reconstruction is one of the MVP's success criteria, so it is a tab on
 * the message you are already reading rather than a separate destination —
 * switching never costs you your place in the results.
 */

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { getEmail, getThread } from "@/lib/api";
import type { EmailDoc, EmailHit, ThreadResponse } from "@/lib/types";
import { cleanText, longDate, personName, plural, shortDate } from "@/lib/format";
import { Avatar } from "./Avatar";

export function ReadingPane({
  hit,
  onClose,
  saved,
  onToggleSave,
}: {
  hit: EmailHit | null;
  onClose: () => void;
  saved: boolean;
  onToggleSave: () => void;
}) {
  const [tab, setTab] = useState<"message" | "thread">("message");
  const [doc, setDoc] = useState<EmailDoc | null>(null);
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTab("message");
  }, [hit?.id]);

  useEffect(() => {
    if (!hit) return;
    const ac = new AbortController();
    setDoc(null);
    setError(null);
    getEmail(hit.id, ac.signal)
      .then(setDoc)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== "AbortError") setError(e.message);
      });
    return () => ac.abort();
  }, [hit]);

  useEffect(() => {
    if (!hit || tab !== "thread") return;
    const ac = new AbortController();
    setThread(null);
    getThread(hit.thread_id, ac.signal)
      .then(setThread)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== "AbortError") setError(e.message);
      });
    return () => ac.abort();
  }, [hit, tab]);

  if (!hit) {
    return (
      <div className="card grid h-full min-h-[320px] place-items-center px-8 py-16 text-center">
        <div>
          <p className="font-serif text-[1.125rem]">Select a result to read it</p>
          <p className="meta mx-auto mt-1.5 max-w-[34ch]">
            The full message opens here, with its thread on the next tab.
          </p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      key={hit.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
      className="card flex h-full flex-col overflow-hidden"
    >
      <header className="flex items-center gap-1 border-b border-[var(--color-rule)] px-4 py-2.5">
        <nav className="flex gap-1" role="tablist">
          {(["message", "thread"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={[
                "relative rounded px-2.5 py-1 text-[0.875rem] capitalize transition-colors",
                tab === t
                  ? "font-semibold"
                  : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
              ].join(" ")}
            >
              {t}
              {tab === t && (
                <motion.span
                  layoutId="pane-tab"
                  className="absolute inset-x-1.5 -bottom-[11px] h-0.5 rounded-full bg-[var(--color-ink)]"
                />
              )}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1">
          <IconButton onClick={onToggleSave} label={saved ? "Remove from saved" : "Save"}>
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path
                d="M8 1.9l1.85 3.75 4.15.6-3 2.93.71 4.12L8 11.35l-3.71 1.95.71-4.12-3-2.93 4.15-.6L8 1.9z"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinejoin="round"
                fill={saved ? "var(--color-marker-key-solid)" : "none"}
              />
            </svg>
          </IconButton>
          <IconButton onClick={onClose} label="Close">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </IconButton>
        </div>
      </header>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {error && <p className="px-5 py-8 text-[var(--color-muted)]">{error}</p>}
        {!error && tab === "message" && <Message doc={doc} />}
        {!error && tab === "thread" && <Thread thread={thread} currentId={hit.id} />}
      </div>
    </motion.div>
  );
}

function IconButton({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid size-7 place-items-center rounded-full text-[var(--color-muted)] transition-colors hover:bg-[var(--color-sunk)] hover:text-[var(--color-ink)]"
    >
      {children}
    </button>
  );
}

function Message({ doc }: { doc: EmailDoc | null }) {
  if (!doc) return <Loading />;

  return (
    <article className="px-5 py-5">
      <h2 className="font-serif text-[1.35rem] leading-tight tracking-[-0.015em]">
        {doc.subject}
      </h2>

      <div className="mt-4 flex items-start gap-3 border-b border-[var(--color-rule)] pb-4">
        <Avatar address={doc.from} name={doc.from_name} size={36} />
        <div className="min-w-0 flex-1">
          <p className="text-[0.875rem]">
            <span className="font-semibold">{doc.from_name || personName(doc.from)}</span>{" "}
            <span className="text-[var(--color-muted)]">&lt;{doc.from}&gt;</span>
          </p>
          <p className="meta truncate">to {doc.to.map(personName).join(", ")}</p>
          {doc.cc.length > 0 && (
            <p className="meta truncate">cc {doc.cc.map(personName).join(", ")}</p>
          )}
        </div>
        <time className="meta num shrink-0" dateTime={doc.date}>
          {longDate(doc.date)}
        </time>
      </div>

      <div className="prose-mail mt-5">{cleanText(doc.body)}</div>

      {doc.quoted_text && (
        <details className="mt-5 border-t border-[var(--color-rule)] pt-4">
          <summary className="meta cursor-pointer select-none hover:text-[var(--color-ink)]">
            Quoted text from earlier messages
          </summary>
          <div className="prose-mail mt-3 text-[var(--color-muted)]">{doc.quoted_text}</div>
        </details>
      )}

      {doc.attachment_names.length > 0 && (
        <section className="mt-6 border-t border-[var(--color-rule)] pt-4">
          <p className="mb-2 text-[0.8125rem] font-semibold">
            {doc.attachment_names.length === 1
              ? "1 attachment"
              : `${doc.attachment_names.length} attachments`}
          </p>
          <ul className="flex flex-wrap gap-2">
            {doc.attachment_names.map((a) => (
              <li
                key={a}
                className="flex items-center gap-2 rounded-lg border border-[var(--color-rule)] px-2.5 py-1.5 text-[0.8125rem]"
              >
                <FileGlyph name={a} />
                <span className="truncate">{a}</span>
              </li>
            ))}
          </ul>
          <p className="meta mt-2 text-[var(--color-faint)]">
            The corpus records attachment names only; the files themselves were not
            part of the release.
          </p>
        </section>
      )}

      {doc.duplicate_count > 1 && (
        <p className="meta mt-5">
          This message was found in {doc.duplicate_count} mailboxes and stored once.
        </p>
      )}

      <p className="mono mt-6 break-all text-[var(--color-faint)]">{doc.message_id}</p>
    </article>
  );
}

/** Colour-codes a file by extension, the way a mail client would. */
function FileGlyph({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const tint =
    ext === "pdf" ? "#c85a4a" : ext === "xls" || ext === "xlsx" ? "#3f8e5c" : "#4a72b8";
  return (
    <span
      className="grid size-5 shrink-0 place-items-center rounded text-[0.5rem] font-bold text-white"
      style={{ background: tint }}
      aria-hidden
    >
      {ext.slice(0, 3).toUpperCase()}
    </span>
  );
}

function Thread({ thread, currentId }: { thread: ThreadResponse | null; currentId: string }) {
  if (!thread) return <Loading />;

  return (
    <div className="px-5 py-5">
      <h2 className="font-serif text-[1.25rem] leading-tight tracking-[-0.015em]">
        {thread.subject}
      </h2>
      <p className="meta mt-1">
        {plural(thread.messages.length, "message")}, {shortDate(thread.messages[0].date)} to{" "}
        {shortDate(thread.messages[thread.messages.length - 1].date)}
      </p>

      {/* One spine carries the eye down the conversation in time order. */}
      <ol className="relative mt-5 space-y-5 border-l border-[var(--color-rule)] pl-5">
        {thread.messages.map((m) => {
          const current = m.id === currentId;
          return (
            <li key={m.id} className="relative">
              <span
                className="absolute -left-[26px] top-1.5 size-2 rounded-full ring-4 ring-[var(--color-surface)]"
                style={{
                  background: current ? "var(--color-ink)" : "var(--color-rule-strong)",
                }}
                aria-hidden
              />
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[0.875rem] font-semibold">
                  {m.from_name || personName(m.from)}
                </span>
                <time className="meta num shrink-0" dateTime={m.date}>
                  {shortDate(m.date)}
                </time>
              </div>
              <p className="meta">to {m.to.map(personName).join(", ")}</p>
              <p
                className={[
                  "prose-mail mt-2 text-[0.875rem]",
                  current ? "" : "line-clamp-2 text-[var(--color-muted)]",
                ].join(" ")}
              >
                {cleanText(m.body)}
              </p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Loading() {
  return (
    <div className="space-y-3 px-5 py-5" aria-label="Loading">
      <div className="shimmer h-5 w-3/4" />
      <div className="shimmer h-3 w-1/2" />
      <div className="mt-5 space-y-2">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="shimmer h-3" style={{ width: `${92 - i * 7}%` }} />
        ))}
      </div>
    </div>
  );
}
