"use client";

/**
 * The hero's paper collage.
 *
 * Drawn entirely as inline SVG and type rather than photography: the archive is
 * correspondence, so the page is built from letters, postcards and an engraved
 * landmark. It sits behind the content at low contrast, is decorative only
 * (`aria-hidden`), and never intercepts a click.
 */

export function Collage() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {/* A large engraving bled off the bottom-left corner, kept faint enough
          to read as a watermark rather than an illustration. */}
      <Dome className="absolute -bottom-24 -left-24 w-[300px] opacity-[0.045] sm:w-[400px]" />

      {/* Handwritten note, upper left. */}
      <p className="script absolute left-[3.5%] top-[24%] hidden w-[185px] -rotate-[7deg] text-[1.3rem] leading-[1.55] text-[var(--color-faint)] opacity-60 lg:block">
        Answers from your conversations
      </p>

      {/* Postcard stack, upper right. */}
      <div className="absolute right-[2%] top-[10%] hidden h-[290px] w-[330px] xl:block">
        {/* Two cards behind, fanned. */}
        <div className="absolute right-[22px] top-[26px] h-[232px] w-[168px] rotate-[8deg] rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-surface)] opacity-55" />
        <div className="absolute right-[64px] top-[10px] h-[236px] w-[164px] -rotate-[4deg] rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-surface)] opacity-75" />

        {/* The engraved card sits in front. */}
        <div className="absolute right-[104px] top-[30px] h-[196px] w-[150px] rotate-[2deg] overflow-hidden rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-sunk)]">
          <Dome className="absolute -bottom-6 left-1/2 w-[168px] -translate-x-1/2 opacity-[0.22]" />
        </div>

        {/* The caption is its own slip of paper, set as one tracked column. */}
        <div className="absolute right-[6px] top-[34px] flex w-[92px] -rotate-[1deg] flex-col gap-[5px] rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-surface)] px-3 py-4 text-[0.625rem] font-medium tracking-[0.26em] text-[var(--color-faint)]">
          {["EMAILS", "CONNECT", "PEOPLE", "IDEAS", "AND A", "LITTLE", "HISTORY"].map((w) => (
            <span key={w}>{w}</span>
          ))}
        </div>
      </div>

      {/* A torn scrap weighting the left edge. */}
      <div className="absolute -left-10 top-[52%] hidden h-[118px] w-[118px] rotate-[13deg] rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-surface)] opacity-40 lg:block" />
    </div>
  );
}

/** A classical dome, drawn in the manner of a line engraving. */
function Dome({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 210" fill="none" className={className}>
      <g
        stroke="var(--color-ink)"
        strokeWidth="1.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* Finial. */}
        <path d="M100 16v9" />
        <circle cx="100" cy="12" r="3" />
        <path d="M89 42c0-6.6 4.9-11.5 11-11.5S111 35.4 111 42" />
        <path d="M86 42h28" />

        {/* Dome shell and ribs. */}
        <path d="M60 100c0-24.8 17.9-44 40-44s40 19.2 40 44" />
        <path d="M100 56v44" />
        <path d="M80 62c-6.6 11.4-9.6 24.4-9.6 38M120 62c6.6 11.4 9.6 24.4 9.6 38" />
        <path d="M68 82c9.8-5.2 20.6-7.8 32-7.8s22.2 2.6 32 7.8" />

        {/* Drum with arched windows. */}
        <path d="M60 100h80M64 100v28M136 100v28M64 128h72" />
        {[73, 89, 105, 121].map((x) => (
          <path key={x} d={`M${x} 122v-11a3.6 3.6 0 017.2 0v11z`} />
        ))}

        {/* Colonnade. */}
        <path d="M52 128h96M56 128v50M144 128v50" />
        {[70, 86, 102, 118, 134].map((x) => (
          <path key={x} d={`M${x} 133v42`} />
        ))}
        <path d="M48 178h104M44 186h112" />

        {/* Steps. */}
        <path d="M40 194h120M36 202h128" />
      </g>
    </svg>
  );
}
