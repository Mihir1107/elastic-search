"use client";

/**
 * Renders an Elasticsearch highlight fragment.
 *
 * ES returns fragments containing <em> around matched terms. We re-render
 * those as marker strokes rather than trusting the HTML: the fragment is split
 * on the tags and rebuilt from text nodes, so nothing from a document body can
 * inject markup. `ink` picks which marker the match gets — yellow when the
 * keyword leg produced it, blue when it came from the semantic leg.
 */

export function Marker({
  fragment,
  ink = "key",
  className = "",
}: {
  fragment: string;
  ink?: "key" | "sem";
  className?: string;
}) {
  const parts = fragment.split(/(<em>.*?<\/em>)/g).filter(Boolean);

  return (
    <span className={className}>
      {parts.map((part, i) => {
        const m = part.match(/^<em>(.*?)<\/em>$/s);
        if (!m) return <span key={i}>{decode(part)}</span>;
        return (
          <mark key={i} className={`mk mk-${ink}`}>
            {decode(m[1])}
          </mark>
        );
      })}
    </span>
  );
}

/**
 * Undo the escaping Elasticsearch's html encoder applies to the source text.
 *
 * Decoding by hand rather than via innerHTML keeps the guarantee above: the
 * result is only ever used as a text node, so a document that contains markup
 * still cannot render it. ES emits apostrophes as the hex entity `&#x27;`, not
 * the decimal `&#39;`, so numeric entities are handled in both forms; `&amp;`
 * is decoded last so "&amp;lt;" survives as the literal text "&lt;".
 */
const NAMED: Record<string, string> = {
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&apos;": "'",
  "&nbsp;": "\u00a0",
};

function decode(s: string): string {
  let out = s.replace(/&#(x[0-9a-f]+|\d+);/gi, (_, code: string) => {
    const point =
      code[0].toLowerCase() === "x"
        ? Number.parseInt(code.slice(1), 16)
        : Number.parseInt(code, 10);
    return Number.isFinite(point) && point > 0 ? String.fromCodePoint(point) : _;
  });
  for (const [entity, char] of Object.entries(NAMED)) {
    out = out.split(entity).join(char);
  }
  return out.split("&amp;").join("&");
}
