import { Link, useLocation } from "react-router-dom";
import { Glyph } from "./Glyph";

export const SiteHeader = () => {
  const { pathname } = useLocation();
  const onAbout = pathname === "/about";

  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-sky/80 backdrop-blur-md">
      <div className="container flex h-14 items-center justify-between">
        <Link to="/" className="group flex items-center gap-2.5">
          <Glyph variant="seal" className="h-6 w-6 text-moss transition-transform group-hover:rotate-6" />
          <span className="font-serif text-xl tracking-wide text-ink">Poneglyph</span>
        </Link>

        <Link
          to={onAbout ? "/" : "/about"}
          className="inline-flex items-center gap-2 border border-border bg-secondary/60 px-3 py-1.5 text-[11px] uppercase tracking-widest text-ink/70 transition-colors hover:border-moss/60 hover:text-moss"
        >
          <Glyph variant={onAbout ? "ask" : "tablet"} className="h-3.5 w-3.5" />
          {onAbout ? "Back to Robin" : "About"}
        </Link>
      </div>
    </header>
  );
};
