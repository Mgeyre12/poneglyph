import { useState } from "react";
import { Glyph } from "./Glyph";
import { cn } from "@/lib/utils";

type Props = {
  chapter: number | string;
  title?: string;
  className?: string;
};

/** Stone-tablet citation pill — chapter references in Robin's answers. */
export const CitationPill = ({ chapter, title, className }: Props) => {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className={cn(
          "mx-0.5 inline-flex items-center gap-1 rounded-sm border border-stone-deep/50 bg-stone px-1.5 py-px align-baseline",
          "font-sans text-[11px] tracking-wider text-engraved shadow-tablet",
          "transition-all hover:border-moss/60 hover:bg-stone-deep",
          className,
        )}
      >
        <Glyph variant="tablet" className="h-2.5 w-2.5" />
        Ch. {chapter}
      </button>
      {open && title && (
        <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 -translate-x-1/2 whitespace-nowrap rounded-sm border border-stone-deep/40 bg-stone px-2 py-1 font-serif text-xs italic text-engraved shadow-tablet">
          {title}
        </span>
      )}
    </span>
  );
};
