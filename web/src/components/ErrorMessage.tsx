import { useEffect, useState } from "react";
import { Glyph } from "@/components/Glyph";
import { BackendError, RateLimitError, TurnstileError } from "@/lib/errors";

type ErrorKind = "RateLimitError" | "TurnstileError" | "BackendError" | "Unknown";

const ERROR_TAGS: Record<ErrorKind, string> = {
  RateLimitError: "TOO MANY QUESTIONS",
  TurnstileError: "GATE CLOSED",
  BackendError: "STONES DISTURBED",
  Unknown: "SOMETHING BROKE",
};

const ERROR_VOICES: Record<ErrorKind, string> = {
  RateLimitError: "The stones grow quiet — too many hands at once.",
  TurnstileError: "The gate didn't recognize this request. Try again.",
  BackendError: "Something disturbed the record. Give me a moment and ask again.",
  Unknown: "Something unexpected broke the thread.",
};

export const MAX_RETRIES = 3;
const DEFAULT_RATE_LIMIT_SECONDS = 60;
const EXHAUSTED_TEXT =
  "The stones remain silent. Try a different question, or come back later.";

function errorKind(err: unknown): ErrorKind {
  if (err instanceof RateLimitError) return "RateLimitError";
  if (err instanceof TurnstileError) return "TurnstileError";
  if (err instanceof BackendError) return "BackendError";
  return "Unknown";
}

interface ErrorMessageProps {
  error: unknown;
  retryCount: number;
  retryInFlight: boolean;
  onRetry: () => void;
}

export const ErrorMessage = ({
  error,
  retryCount,
  retryInFlight,
  onRetry,
}: ErrorMessageProps) => {
  const kind = errorKind(error);
  const exhausted = retryCount >= MAX_RETRIES;

  const rateLimit = error instanceof RateLimitError ? error : null;
  const hasExplicitRetryAfter = rateLimit?.retryAfter != null;
  const initialSeconds = rateLimit
    ? rateLimit.retryAfter ?? DEFAULT_RATE_LIMIT_SECONDS
    : 0;
  const [secondsLeft, setSecondsLeft] = useState(initialSeconds);

  useEffect(() => {
    if (!rateLimit) return;
    setSecondsLeft(rateLimit.retryAfter ?? DEFAULT_RATE_LIMIT_SECONDS);
    const interval = setInterval(() => {
      setSecondsLeft((s) => (s <= 0 ? 0 : s - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [error, rateLimit]);

  const rateLimitPending = !!rateLimit && secondsLeft > 0;
  const buttonDisabled = retryInFlight || rateLimitPending;

  let buttonLabel = "Try again";
  if (retryInFlight) buttonLabel = "Trying again…";
  else if (rateLimitPending) {
    buttonLabel = hasExplicitRetryAfter
      ? `Try again in ${secondsLeft}s`
      : "Try again shortly";
  }

  return (
    <div className="animate-fade-in-up">
      <div className="surface-parchment relative rounded-sm border border-parchment-deep/60 px-7 py-5 shadow-soft">
        <span className="absolute bottom-4 left-3 top-4 w-px bg-moss/20" />
        <div className="pl-4">
          <div className="mb-2 text-[10px] font-sans uppercase tracking-[0.3em] text-brass-dim">
            {ERROR_TAGS[kind]}
          </div>
          <p className="font-serif text-[16px] italic leading-relaxed text-ink/80">
            {ERROR_VOICES[kind]}
          </p>
          <div className="mt-4">
            {exhausted ? (
              <p className="font-serif text-sm italic text-muted-foreground">
                {EXHAUSTED_TEXT}
              </p>
            ) : (
              <button
                onClick={onRetry}
                disabled={buttonDisabled}
                className="inline-flex items-center gap-2 border border-border bg-sky/60 px-3 py-1.5 text-[11px] uppercase tracking-widest text-ink/70 transition-colors hover:border-moss/50 hover:text-moss disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Glyph variant="dot" className="h-3 w-3" />
                {buttonLabel}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
