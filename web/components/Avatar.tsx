"use client";

/**
 * Initial-in-a-circle for a person. The corpus has no profile pictures, so the
 * colour is derived from the address: the same person is always the same
 * colour, which makes a sender recognisable down a long result list.
 */

import { personName } from "@/lib/format";

const TINTS = [
  { bg: "#dbe4f3", fg: "#3a5580" },
  { bg: "#f3dde5", fg: "#84405a" },
  { bg: "#f5e6c8", fg: "#7d6224" },
  { bg: "#d9e8db", fg: "#3d6344" },
  { bg: "#e4dcf0", fg: "#584479" },
  { bg: "#f0e0d4", fg: "#7d5335" },
];

function tintFor(key: string) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return TINTS[h % TINTS.length];
}

export function Avatar({
  address,
  name,
  size = 34,
}: {
  address: string;
  name?: string;
  size?: number;
}) {
  const label = name || personName(address);
  const tint = tintFor(address || label);

  return (
    <span
      className="grid shrink-0 place-items-center rounded-full font-semibold"
      style={{
        width: size,
        height: size,
        background: tint.bg,
        color: tint.fg,
        fontSize: size * 0.4,
      }}
      title={label}
      aria-hidden
    >
      {label.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}
