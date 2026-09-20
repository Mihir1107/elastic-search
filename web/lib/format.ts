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

/**
 * Repair the CALO corpus's mangled smart punctuation for display.
 *
 * The raw maildir stores a right single quote as a control byte plus an ASCII
 * tail, so "Enron's" arrives as "Enron\x01,s" and paints as "Enron ,s". The
 * ingest parser now repairs this at the source, but the serving index predates
 * that fix, so the UI cleans what it is given. Harmless once the index is
 * rebuilt — there is simply nothing left to replace.
 */
export function cleanText(text: string): string {
  return text
    .replace(/\u0001[,'8]/g, "’")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
}
