import { Link } from "react-router-dom";
import { Glyph } from "./Glyph";

export const SiteFooter = () => (
  <footer className="border-t border-border/60 bg-sky-deep/20">
    <div className="container py-10">
      <div className="divider-glyph mb-8">
        <Glyph variant="dot" className="h-3 w-3 text-moss" />
      </div>
      <div className="flex flex-col items-center gap-4 text-xs tracking-widest text-muted-foreground sm:flex-row sm:justify-between">
        <div className="flex items-center gap-2 font-serif text-base tracking-wide text-ink/80">
          <Glyph variant="seal" className="h-4 w-4 text-moss" />
          Poneglyph
        </div>
        <div className="flex items-center gap-6 uppercase">
          <Link to="/about" className="hover:text-moss transition-colors">About</Link>
          <a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-moss transition-colors">GitHub</a>
          <span className="text-muted-foreground/70">Built by Mussa</span>
        </div>
      </div>
      <p className="mt-4 text-center text-[10px] uppercase tracking-[0.3em] text-muted-foreground/70">
        Powered by Claude · Neo4j
      </p>
    </div>
  </footer>
);
