const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * Readable name for an address. The API returns `from_name` for senders, so
 * this is for recipients and facet keys, where only the address is known.
 */
export function personName(address: string): string {
  const local = address.split("@")[0] ?? address;
  return local
    .split(/[._-]/)
    .filter(Boolean)
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join(" ");
}

export function shortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function longDate(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${shortDate(iso)} at ${hh}:${mm} UTC`;
}

/** "Aug 2001". The two-digit form reads as a day-of-month, which this corpus
 *  (1999-2002) makes genuinely ambiguous. */
export function monthLabel(iso: string): string {
  const d = new Date(iso);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function count(n: number): string {
  return n.toLocaleString("en-US");
}

/** "1,204 emails" / "1 email" */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${count(n)} ${n === 1 ? one : many}`;
}

export function ms(n: number): string {
  return n >= 100 ? `${Math.round(n)} ms` : `${n.toFixed(1)} ms`;
}

/** Recipient list, trimmed with an honest overflow count. */
export function recipients(to: string[], limit = 2): string {
  const names = to.map(personName);
  if (names.length <= limit) return names.join(", ");
  return `${names.slice(0, limit).join(", ")} and ${names.length - limit} more`;
}

/** A line that starts a list item, a quote or a signature rule: never joined. */
const STRUCTURED = /^\s*([-*•>]|\d+[.)]\s|[A-Z][\w ]{0,24}:\s|_{3,}|-{3,}|={3,})/;

/**
 * Undo the fixed-width wrapping mail clients of the era applied (~72 columns),
 * for display only.
 *
 * Within a paragraph, lines are joined when they look hard-wrapped: long, and
 * not list items, quotes or header-like lines. Anything short or structured —
 * addresses, tables, signatures — keeps its line breaks. The original text is
 * always one click away in the reading pane, and export and search never see
 * this.
 */
export function reflow(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((para) => {
      const lines = para.split("\n");
      if (lines.length < 2) return para;
      const out: string[] = [lines[0]];
      for (let i = 1; i < lines.length; i++) {
        const prev = out[out.length - 1];
        const line = lines[i];
        const wrapped =
          lines[i - 1].trimEnd().length >= 45 &&
          line.trim().length > 0 &&
          !STRUCTURED.test(line) &&
          !STRUCTURED.test(lines[i - 1]);
        if (wrapped) out[out.length - 1] = `${prev.trimEnd()} ${line.trimStart()}`;
        else out.push(line);
      }
      return out.join("\n");
    })
    .join("\n\n");
}
