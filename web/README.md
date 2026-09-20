# web — Ledger frontend

Next.js 15 (App Router) + React 19 + TypeScript + Tailwind v4.

## Run it

```bash
make web-install     # npm ci, from the committed lockfile
make web             # dev server on http://localhost:3000
```

It starts against a **fixture corpus** and needs no cluster and no API. To point it
at the real search API:

```bash
cp .env.local.example .env.local
# set NEXT_PUBLIC_USE_MOCK=false and API_BASE_URL=http://localhost:8000
```

## How it is put together

| Path | What it is |
|---|---|
| `app/page.tsx` | State + the landing/workspace swap |
| `components/Landing.tsx` | Entry screen, hero collage, typing hints |
| `components/Workspace.tsx` | Three-column results view |
| `app/api/proxy/[...path]/route.ts` | Server-side passthrough to FastAPI |
| `lib/types.ts` | View models the components render |
| `lib/adapt.ts` | Maps the FastAPI wire format onto those view models |
| `lib/api.ts` | The only module that knows mock-vs-real |
| `lib/query.ts` | Client mirror of the parser, used to draw chips in the search box |
| `lib/mock/` | Fixture corpus and a stand-in retrieval pipeline |

`lib/adapt.ts` is the single place the API contract is pinned down. If the API
changes shape, that file changes and nothing else does.

## The three things worth knowing

**The search box decodes itself.** A transparent `<input>` sits on top of a mirror
layer that paints each token in the colour of what the parser made of it — person,
phrase, date bound, or plain text. Both layers must produce identical text metrics,
so chips are drawn with `background` and `box-shadow` only, never padding, which
would shift the glyphs. See `.field-stack` in `app/globals.css`.

**Two marker inks explain each result.** Yellow marks terms the keyword leg matched;
blue marks the chunk the vector leg returned. A result matched only on meaning looks
visibly different from one both legs agreed on.

**The search bar travels rather than being replaced.** Landing and Workspace each render
one element with `layoutId="search-pill"` inside a `LayoutGroup`, and the swap between
them is synchronous — which is what shared-layout animation requires, and why there is no
`AnimatePresence` around the two views. See DECISIONS.md D19 before reintroducing one.

## Caveats

The fixtures in `lib/mock/corpus.ts` are synthetic sample text, not real Enron mail,
and are not evaluation data. `lib/adapt.ts` was written against `api/app/models.py`
and has not yet been run against a live API — see DECISIONS.md D16 for the two fields
that are approximations.
