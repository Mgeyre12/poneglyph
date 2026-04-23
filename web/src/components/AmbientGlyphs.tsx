import { useEffect, useState } from "react";

const GLYPHS = [
  "◰", "◳", "◱", "◲", "▣", "◫", "⌘", "⌬", "⎔", "⏣",
  "▤", "▥", "▦", "▧", "▨", "▩", "◧", "◨", "◩", "◪",
  "⌗", "⌖", "⏥", "⌸", "⌹", "⌺", "⌻", "⌼", "⍃", "⍌",
  "⍍", "⍎", "⍓", "⍔", "⍕", "⍖", "⎅", "⎆", "⎇", "⏚",
];

type Drift = {
  id: number;
  ch: string;
  x: number;
  y: number;
  size: number;
  rot: number;
  duration: number;
};

/** Atmospheric drifting glyphs — red Poneglyph carvings flickering across the page. */
export const AmbientGlyphs = () => {
  const [items, setItems] = useState<Drift[]>([]);

  useEffect(() => {
    let id = 0;
    const spawn = () => {
      // Spawn anywhere on screen, not just corners
      const item: Drift = {
        id: id++,
        ch: GLYPHS[Math.floor(Math.random() * GLYPHS.length)],
        x: Math.random() * 95,
        y: Math.random() * 95,
        size: 28 + Math.random() * 44,
        rot: -12 + Math.random() * 24,
        duration: 6 + Math.random() * 4,
      };
      setItems((prev) => [...prev, item]);
      setTimeout(
        () => setItems((prev) => prev.filter((p) => p.id !== item.id)),
        item.duration * 1000,
      );
    };

    // Seed a handful immediately so they're visibly present
    for (let k = 0; k < 8; k++) {
      setTimeout(spawn, k * 250);
    }
    const i = setInterval(spawn, 1400);
    return () => { clearInterval(i); };
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {items.map((it) => (
        <span
          key={it.id}
          className="absolute font-serif text-crimson/45 animate-glyph-drift select-none"
          style={{
            left: `${it.x}%`,
            top: `${it.y}%`,
            fontSize: it.size,
            transform: `rotate(${it.rot}deg)`,
            animationDuration: `${it.duration}s`,
            textShadow: "0 1px 0 hsl(var(--crimson-bright) / 0.35)",
          }}
        >
          {it.ch}
        </span>
      ))}
    </div>
  );
};
