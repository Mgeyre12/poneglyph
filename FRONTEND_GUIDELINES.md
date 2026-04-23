# FRONTEND_GUIDELINES.md

**Read this before touching anything under `web/`.** It is the design contract for the Poneglyph frontend. If this file and the code disagree, update this file to match the code — do not drift.

---

## Stack

- **Build:** Vite 5 + `@vitejs/plugin-react-swc`
- **Language:** TypeScript, React 18
- **Styling:** Tailwind CSS 3 + CSS custom properties (HSL) + `tailwind-merge` / `clsx`
- **UI primitives:** shadcn/ui (Radix-based) under `src/components/ui/` — do not hand-edit these; regenerate via the shadcn CLI if an upgrade is needed
- **Routing:** `react-router-dom` v6 (`<BrowserRouter>` in `src/App.tsx`)
- **Data:** `@tanstack/react-query` provider is already wrapped at the root
- **Markdown rendering:** `react-markdown` (used for Robin's answers)
- **Graph viz (placeholder for v2):** `react-force-graph-2d`
- **Testing:** `vitest` + `@testing-library/react` + `jsdom`
- **Lovable tagger:** `lovable-tagger` is installed as a dev dep and injected via `vite.config.ts` in dev mode. It is harmless — leave it in unless we fully decouple from Lovable.

Do **not** propose Next.js, App Router, or any SSR framework. The product is a Vite SPA.

## Project layout (inside `web/`)

```
web/
├── index.html                # Vite entry
├── vite.config.ts            # Dev server port 8080, "@" → ./src
├── tailwind.config.ts        # Design tokens wired to CSS vars
├── components.json           # shadcn config
├── src/
│   ├── main.tsx              # Root render
│   ├── App.tsx               # Router + providers (QueryClient, Tooltip, Toaster)
│   ├── index.css             # THE design system — tokens, surfaces, animations
│   ├── pages/
│   │   ├── Ask.tsx           # / — Robin chat
│   │   ├── About.tsx         # /about — codex folio
│   │   └── NotFound.tsx      # catch-all
│   ├── components/
│   │   ├── SiteHeader.tsx    # Sticky top nav
│   │   ├── SiteFooter.tsx
│   │   ├── AmbientGlyphs.tsx # Background drift layer
│   │   ├── Glyph.tsx         # Inline glyph icons (seal/node/tablet/ask/dot)
│   │   ├── CitationPill.tsx  # [[Ch.NNN|Title]] → pill renderer
│   │   ├── KnowledgeGraph.tsx
│   │   ├── NavLink.tsx
│   │   └── ui/               # shadcn primitives — do not hand-edit
│   ├── lib/
│   │   ├── askRobin.ts       # STUB — stays until Stage 6
│   │   └── utils.ts          # cn() helper
│   ├── hooks/                # use-toast, use-mobile
│   └── test/                 # vitest setup + example
```

## Dev server

```bash
cd web
npm install
npm run dev        # http://localhost:8080 (configured in vite.config.ts, NOT 5173)
npm run build
npm run test
```

The Vite dev server is pinned to port **8080** with `host: "::"` so it binds all interfaces. If you change the port, update this doc and any Railway/Vercel origin references.

## Design language — "sunlit ruin overgrown by jungle"

A fan reading Poneglyphs on a quiet beach in a ruined temple. Bright atmospheric sky, weathered blue-grey stone, mossy edges, aged parchment, brass accents, and rare crimson for the Red Poneglyph. **Light-themed product** — there is no dark mode. `index.css` hard-codes `color-scheme: light` and the `.dark` class does nothing meaningful.

**Aesthetic rules — hold these firm:**

- **No purple gradients, no neon, no "AI startup" look.** This is not a SaaS dashboard.
- **No emoji** in UI copy. Use the `<Glyph>` component for inline symbols and the ambient SVG glyph patterns from `index.css` (`.glyph-bg`, `.text-glyph`) for decoration.
- **No hex, no rgb(), no raw Tailwind color classes like `bg-purple-500`.** Every color comes from a token (see below).
- **No drop shadows outside the three defined shadow variables** (`--shadow-carved`, `--shadow-tablet`, `--shadow-soft`).
- **No toast/alert popups for Robin-facing errors.** Error states must render as parchment or stone surfaces in-flow (Stage 7 will formalize this).
- **Serif is the personality.** Cormorant Garamond for all display type. Italicize Robin's voice lines.

## Color tokens (all HSL, all in `src/index.css`)

Defined under `:root` and exposed via Tailwind in `tailwind.config.ts`. **Always use the Tailwind class or `hsl(var(--token))`, never the raw HSL numbers.**

| Token | Tailwind | Purpose |
|---|---|---|
| `--background` | `bg-background` | Sky/sea base — bright atmospheric backdrop |
| `--foreground` | `text-foreground` | Default body text (ink) |
| `--card` / `--stone` | `bg-card`, `bg-stone` | The Poneglyph slab — cool blue-grey carved stone |
| `--stone-deep` | `bg-stone-deep` | Deeper slab tone for pressed/hover |
| `--stone-light` | `bg-stone-light` | Lighter slab tone |
| `--primary` / `--moss` | `bg-primary`, `text-moss` | Mossy green — the overgrowth, Robin's voice color |
| `--moss-bright`, `--moss-dark` | `bg-moss-bright`, `text-moss-dark` | Moss variants |
| `--secondary` / `--parchment` | `bg-secondary`, `bg-parchment` | Aged parchment/sand — Robin's journal page |
| `--parchment-deep` | `bg-parchment-deep` | Parchment border/shadow |
| `--accent` / `--brass` | `bg-accent`, `text-brass` | Brass — interactive highlight, ring color |
| `--brass-dim` | `text-brass-dim` | Muted brass |
| `--destructive` / `--crimson` | `bg-destructive`, `bg-crimson` | Red Poneglyph — destructive states, rare accent |
| `--crimson-bright` | `bg-crimson-bright` | Brighter crimson variant |
| `--sky`, `--sky-deep` | `bg-sky`, `bg-sky-deep` | Sky tones for header/input backgrounds |
| `--ocean` | `bg-ocean` | Deep sea accent |
| `--ink` | `text-ink`, `bg-ink` | Near-black for text and overlays |
| `--muted`, `--muted-foreground` | standard shadcn | Muted surfaces/text |
| `--border`, `--input`, `--ring` | standard shadcn | Border, input bg, focus ring |

Adding a new token? Add the HSL tuple to `:root` in `index.css` **and** the color entry in `tailwind.config.ts`. Both. Tailwind won't see it otherwise.

## Gradients & shadows (also tokens)

```
--gradient-sky          → bg-gradient-sky
--gradient-stone        → bg-gradient-stone
--gradient-crimson      → bg-gradient-crimson
--gradient-moss-fade    → bg-gradient-moss-fade

--shadow-carved         → shadow-carved   (inset + outset — for stone slabs)
--shadow-tablet         → shadow-tablet   (lifted tablet feel)
--shadow-soft           → shadow-soft     (generic)
```

## Surface classes

Defined in `@layer components` in `index.css`. These are the building blocks — use them instead of re-stacking backgrounds ad hoc.

- `.surface-stone` — cool blue-grey carved stone with noise + inset shadow. The Poneglyph itself. Use for user messages, send buttons, primary CTAs.
- `.moss-edges` — adds mossy radial gradients creeping in from the corners. Pairs with `.surface-stone` or `.surface-crimson`. Content must sit in a direct child to rise above the `::before` moss layer (the class handles z-index for direct children).
- `.surface-crimson` — the Red Poneglyph variant. Rare. Use only for emphasis that actually maps to canon red-poneglyph lore.
- `.surface-parchment` — aged paper with noise + vignette. Robin's answer body.
- `.text-engraved` — chiseled light text for on-stone headings.
- `.text-engraved-dark` — chiseled dark text on parchment.
- `.divider-glyph` — horizontal divider with a centered glyph slot.

## Animation & motion

All keyframes live in `index.css` at the bottom. Prefer these over one-off transitions:

- `.animate-glyph-flicker` — soft flicker for idle glyphs
- `.animate-pulse-edge` — edge opacity pulse
- `.animate-fade-in-up` — entrance for new messages/sections
- `.animate-glyph-drift` — ambient glyphs rising through the background
- `.animate-slow-sway` — gentle rotation/sway

Keep motion **slow and subtle**. Poneglyphs do not twitch.

## Typography

- **Display / serif:** `Cormorant Garamond` (`font-serif` in Tailwind, also `.font-serif-display`). Loaded from Google Fonts at the top of `index.css`. Used for headings, Robin's answers, user messages, display numerals.
- **Sans / body:** `Inter` (`font-sans`). Used for meta text, labels, uppercase tracking labels.
- **Italic serif** = Robin speaking. Non-italic serif = static text in Robin's voice.
- **Small caps / uppercase tracking:** `text-[11px] uppercase tracking-widest` or `tracking-[0.3em]` for folio labels and metadata. Always muted.

## The `<Glyph>` component

`src/components/Glyph.tsx` is the ONLY acceptable source of inline symbol glyphs. Variants today: `seal`, `node`, `tablet`, `ask`, `dot`. Add new variants there — do not import `lucide-react` icons directly into pages if a Glyph variant would fit the aesthetic. (Lucide is fine inside `components/ui/` shadcn primitives; they aren't Robin-facing.)

## Citation rendering

Robin's markdown answers embed `[[Ch.NNN|Title]]` tokens inline. The regex `/\[\[Ch\.(\d+)\|([^\]]+)\]\]/g` in `src/pages/Ask.tsx` (`renderWithCitations`) turns each match into a `<CitationPill chapter={n} title="..." />`. Stage 5 backend work must emit these tokens inline in the answer text; Stage 6 wires the real API.

## The `askRobin` contract

`src/lib/askRobin.ts` today is a stub that returns canned answers. Its exported signature is the contract:

```ts
export type RobinAnswer = {
  text: string;
  citations: { chapter: number; title: string }[];
};

export async function askRobin(question: string): Promise<RobinAnswer>;
```

**v1 is a blocking call.** Even though the backend streams over SSE, `askRobin` must buffer internally and only resolve with the full answer + deduped citations. Streaming display, the thinking panel, and incremental citation reveal are Week 11 work — do not introduce them now.

Errors Stage 6 will raise (do not invent new types):

- `RateLimitError` — backend returned 429
- `TurnstileError` — backend returned 403 (Turnstile verification failed)
- `BackendError` — any 5xx or network failure

Error UI is Stage 7 — render as parchment/stone panels in-flow, never as toast/alert popups.

## Robin's voice

Robin (Nico Olvia's daughter, archaeologist, sole living reader of Poneglyphs) is the persona. Every piece of UI copy should sound like her or like a codex she wrote.

- **Tone:** calm, a little weary, respectful of the record, quick to admit silence. She does not oversell.
- **Openings** when appropriate: "An interesting thread.", "Let me read what the stones remember.", "A question close to me."
- **When the graph is silent:** say so. "The record is incomplete here." "The stones do not speak to that." Never fabricate.
- **No hype, no marketing adjectives, no exclamation points.** No "amazing", "awesome", "let's go". Ever.
- **No emoji.** Use a `<Glyph>` if you need a symbol.
- **Chapter citations are sacred.** Claims should bind to a chapter. If they can't, the copy should acknowledge it.
- **About page is a "codex."** Sections are "Folio I", "Folio II"… Labels are small-caps with generous letter-spacing.

## Do / Don't

**Do:**
- Read this file before any visual or structural change to `web/`.
- Use tokens, surface classes, and the `<Glyph>` component.
- Keep Robin's voice consistent with the existing pages.
- Add new tokens in both `index.css` and `tailwind.config.ts`.
- Prefer editing existing components over adding new ones.

**Don't:**
- Hardcode colors, gradients, or shadows.
- Add Next.js, SSR, or a second router.
- Use emoji, purple/neon palettes, drop shadows outside the three token shadows, or toast popups for Robin errors.
- Hand-edit files under `src/components/ui/` (regenerate via shadcn instead).
- Break the `RobinAnswer` contract or make `askRobin` streaming before Week 11.
- Rename the Vite dev port away from 8080 without updating this doc.
