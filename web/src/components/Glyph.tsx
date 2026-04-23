import { cn } from "@/lib/utils";

type GlyphVariant = "seal" | "tablet" | "compass" | "node" | "dot" | "ask" | "read" | "answer";

/**
 * Invented Poneglyph-inspired glyph alphabet.
 * Square, angular, carved-stone aesthetic.
 * NOT a copy of the canonical Poneglyph script.
 */
export const Glyph = ({
  variant = "seal",
  className,
}: {
  variant?: GlyphVariant;
  className?: string;
}) => {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  switch (variant) {
    case "seal":
      return (
        <svg {...common} className={cn(className)}>
          <rect x="3" y="3" width="18" height="18" />
          <rect x="7" y="7" width="10" height="10" />
          <path d="M3 12h4M17 12h4M12 3v4M12 17v4" />
          <rect x="11" y="11" width="2" height="2" fill="currentColor" />
        </svg>
      );
    case "tablet":
      return (
        <svg {...common} className={cn(className)}>
          <path d="M5 4h14v16H5z" />
          <path d="M8 8h8M8 11h6M8 14h8M8 17h4" strokeWidth={1} opacity={0.7} />
        </svg>
      );
    case "compass":
      return (
        <svg {...common} className={cn(className)}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 4l2 8-2 8-2-8z" fill="currentColor" fillOpacity={0.2} />
          <path d="M4 12l8-2 8 2-8 2z" />
        </svg>
      );
    case "node":
      return (
        <svg {...common} className={cn(className)}>
          <circle cx="6" cy="6" r="2.2" fill="currentColor" />
          <circle cx="18" cy="6" r="2.2" />
          <circle cx="6" cy="18" r="2.2" />
          <circle cx="18" cy="18" r="2.2" fill="currentColor" />
          <circle cx="12" cy="12" r="2.2" />
          <path d="M7.5 7.5l3 3M16.5 7.5l-3 3M7.5 16.5l3-3M16.5 16.5l-3-3" opacity={0.6} />
        </svg>
      );
    case "ask":
      return (
        <svg {...common} className={cn(className)}>
          <rect x="4" y="5" width="16" height="12" />
          <path d="M9 21l3-4 3 4" />
          <path d="M9 9h6M9 12h4" />
        </svg>
      );
    case "read":
      return (
        <svg {...common} className={cn(className)}>
          <rect x="4" y="4" width="7" height="16" />
          <rect x="13" y="4" width="7" height="16" />
          <path d="M6 8h3M6 11h3M6 14h3M15 8h3M15 11h3M15 14h3" strokeWidth={1} opacity={0.7} />
        </svg>
      );
    case "answer":
      return (
        <svg {...common} className={cn(className)}>
          <path d="M3 5h18v11H8l-5 5z" />
          <path d="M7 9h10M7 12h7" strokeWidth={1} opacity={0.7} />
        </svg>
      );
    case "dot":
    default:
      return (
        <svg {...common} className={cn(className)}>
          <rect x="9" y="9" width="6" height="6" fill="currentColor" />
          <rect x="3" y="3" width="3" height="3" />
          <rect x="18" y="3" width="3" height="3" />
          <rect x="3" y="18" width="3" height="3" />
          <rect x="18" y="18" width="3" height="3" />
        </svg>
      );
  }
};
