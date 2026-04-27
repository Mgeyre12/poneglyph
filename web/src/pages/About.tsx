import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { Glyph } from "@/components/Glyph";
import { AmbientGlyphs } from "@/components/AmbientGlyphs";
import { API_BASE_URL } from "@/lib/config";

type StatsKey =
  | "characters"
  | "chapters"
  | "organizations"
  | "devil_fruits"
  | "arcs"
  | "locations"
  | "occupations";

type StatsCounts = Record<StatsKey, number>;

const FALLBACK_COUNTS: StatsCounts = {
  characters: 1526,
  chapters: 534,
  organizations: 372,
  devil_fruits: 134,
  arcs: 33,
  locations: 223,
  occupations: 663,
};

const NODE_TYPES: { key: StatsKey; label: string }[] = [
  { key: "characters",    label: "Characters" },
  { key: "chapters",      label: "Chapters" },
  { key: "organizations", label: "Organizations" },
  { key: "devil_fruits",  label: "Devil Fruits" },
  { key: "arcs",          label: "Arcs" },
  { key: "locations",     label: "Locations" },
  { key: "occupations",   label: "Occupations" },
];

const LIMITS = [
  "Haki — its variants and proficiencies are not yet modelled as graph entities.",
  "Combat ability — no power-tier or matchup data; the graph records who, not who would win.",
  "Theory and speculation — only what has been carved into canon. No fan theory validation.",
  "Spoilers past the most recent released chapter — the pipeline tracks the published manga only.",
];

const About = () => {
  const [counts, setCounts] = useState<StatsCounts>(FALLBACK_COUNTS);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/stats`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data: StatsCounts) => {
        if (!cancelled) setCounts(data);
      })
      .catch(() => {
        // Keep FALLBACK_COUNTS — stats failures are silent.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="relative min-h-screen bg-background">
      <AmbientGlyphs />
      <div className="relative z-10">
        <SiteHeader />

        <section className="border-b border-border/60">
          <div className="container py-20">
            <div className="mx-auto max-w-3xl">
              <p className="text-xs uppercase tracking-[0.3em] text-moss">Codex · Folio I</p>
              <h1 className="mt-3 font-serif text-6xl text-ink">On this archive.</h1>
              <div className="mt-8 space-y-5 font-serif text-xl leading-relaxed italic text-ink/85">
                <p>
                  Poneglyph is a record — a graph of what has happened in the world of One Piece, as it was carved.
                </p>
                <p className="not-italic font-sans text-base text-muted-foreground">
                  It contains the people, the places, the powers, and the threads between them.
                  When you ask a question, the system traverses those threads, gathers what is relevant,
                  and returns an answer in the voice of someone who has spent her life reading stones.
                  Every claim is bound to a chapter. Where the record is silent, I will say so.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-border/60 bg-sky-deep/15">
          <div className="container py-20">
            <div className="mx-auto max-w-3xl">
              <p className="text-xs uppercase tracking-[0.3em] text-moss">Folio II</p>
              <h2 className="mt-2 font-serif text-4xl text-ink">The graph contains</h2>
            </div>
            <div className="mx-auto mt-10 grid max-w-5xl grid-cols-2 gap-3 md:grid-cols-4">
              {NODE_TYPES.map((n) => (
                <div key={n.label} className="surface-stone moss-edges border border-stone-deep/40 p-6 text-center">
                  <Glyph variant="node" className="mx-auto h-5 w-5 text-engraved/80" />
                  <p className="mt-3 font-serif text-4xl text-engraved">{counts[n.key].toLocaleString()}</p>
                  <p className="mt-1 text-[11px] uppercase tracking-[0.25em] text-engraved/70">{n.label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-border/60">
          <div className="container py-20">
            <div className="mx-auto max-w-3xl">
              <p className="text-xs uppercase tracking-[0.3em] text-moss">Folio III</p>
              <h2 className="mt-2 font-serif text-4xl text-ink">How the record stays current</h2>
              <p className="mt-6 text-base leading-relaxed text-muted-foreground">
                The graph updates automatically as new chapters are published. A pipeline ingests the latest
                releases, extracts new entities and edges, and reconciles them against the existing record —
                so that what the stones know today reflects what has been carved this week.
              </p>
              <p className="mt-4 text-base leading-relaxed text-muted-foreground">
                Updates run shortly after each weekly release. The system does not invent — it only
                catalogues what has been written.
              </p>
            </div>
          </div>
        </section>

        <section className="border-b border-border/60 bg-sky-deep/15">
          <div className="container py-20">
            <div className="mx-auto max-w-3xl">
              <p className="text-xs uppercase tracking-[0.3em] text-crimson">Folio IV</p>
              <h2 className="mt-2 font-serif text-4xl text-ink">What I can't answer yet</h2>
              <p className="mt-6 text-sm italic text-muted-foreground">
                A scholar is honest about the edges of her knowledge.
              </p>
              <ul className="mt-8 space-y-4">
                {LIMITS.map((l) => (
                  <li key={l} className="flex gap-4 border-l-2 border-crimson/50 pl-5">
                    <p className="font-serif text-lg italic text-ink/85">{l}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <SiteFooter />
      </div>
    </div>
  );
};

export default About;
