import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import { SiteHeader } from "@/components/SiteHeader";
import { Glyph } from "@/components/Glyph";
import { CitationPill } from "@/components/CitationPill";
import { AmbientGlyphs } from "@/components/AmbientGlyphs";
import { askRobin, type RobinAnswer } from "@/lib/askRobin";
import {
  BackendError,
  RateLimitError,
  TurnstileError,
} from "@/lib/errors";
import { TURNSTILE_SITE_KEY } from "@/lib/config";

type Msg =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "robin"; answer: RobinAnswer }
  | { id: string; role: "error"; text: string };

function robinVoiceForError(err: unknown): string {
  if (err instanceof RateLimitError) {
    const wait = err.retryAfter ? ` Try again in about ${err.retryAfter}s.` : "";
    return `The stones grow quiet — too many hands at once.${wait}`;
  }
  if (err instanceof TurnstileError) {
    return "The guardians at the gate didn't recognize you this time. Refresh the page and try again.";
  }
  if (err instanceof BackendError) {
    return "Something disturbed the record. Give me a moment and ask again.";
  }
  return "Something unexpected broke the thread. Ask again in a moment.";
}

const ReadingAnimation = () => {
  const glyphs = ["◰", "◳", "◱", "◲", "▣", "◫", "⌘", "⌬", "⎔", "⏣"];
  return (
    <div className="animate-fade-in-up">
      <div className="mb-3 flex items-center gap-3">
        <Glyph variant="seal" className="h-5 w-5 text-moss animate-glyph-flicker" />
        <span className="font-serif text-lg italic text-moss">Robin</span>
      </div>
      <div className="flex items-center gap-4 pl-8">
        <div className="font-serif text-2xl tracking-[0.3em] text-stone">
          {glyphs.map((g, i) => (
            <span
              key={i}
              className="inline-block animate-glyph-flicker"
              style={{ animationDelay: `${i * 0.12}s` }}
            >
              {g}
            </span>
          ))}
        </div>
        <span className="font-serif text-sm italic text-muted-foreground">Reading the Poneglyphs…</span>
      </div>
    </div>
  );
};

const renderWithCitations = (text: string) => {
  const re = /\[\[Ch\.(\d+)\|([^\]]+)\]\]/g;
  const parts: (string | { ch: number; title: string })[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push({ ch: parseInt(m[1], 10), title: m[2] });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.map((p, i) =>
    typeof p === "string" ? <span key={i}>{p}</span> : <CitationPill key={i} chapter={p.ch} title={p.title} />,
  );
};

function processChildren(children: any): any {
  if (typeof children === "string") return renderWithCitations(children);
  if (Array.isArray(children)) return children.map((c, i) => <span key={i}>{processChildren(c)}</span>);
  return children;
}

const RobinMessage = ({ answer }: { answer: RobinAnswer }) => {
  const [showGraph, setShowGraph] = useState(false);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-4 flex items-center gap-3">
        <Glyph variant="seal" className="h-5 w-5 text-moss" />
        <span className="font-serif text-xl italic text-moss">Robin</span>
        <span className="h-px flex-1 bg-gradient-to-r from-moss/40 to-transparent" />
      </div>

      <div className="surface-parchment relative rounded-sm border border-parchment-deep/60 px-7 py-6 shadow-soft">
        <span className="absolute left-3 top-4 bottom-4 w-px bg-moss/30" />
        <div className="prose prose-sm max-w-none pl-4 font-serif text-[17px] leading-relaxed text-ink prose-strong:text-moss-dark prose-strong:font-semibold prose-em:italic prose-li:my-1">
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-4 last:mb-0">{processChildren(children)}</p>,
              li: ({ children }) => <li>{processChildren(children)}</li>,
            }}
          >
            {answer.text}
          </ReactMarkdown>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3 pl-1">
        <button
          onClick={() => setShowGraph(true)}
          className="inline-flex items-center gap-2 border border-border bg-sky/60 px-3 py-1.5 text-[11px] uppercase tracking-widest text-ink/70 transition-colors hover:border-moss/50 hover:text-moss"
        >
          <Glyph variant="node" className="h-3.5 w-3.5" />
          Show connections
        </button>
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
          {answer.citations.length} citation{answer.citations.length === 1 ? "" : "s"}
        </span>
      </div>

      {showGraph && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-6 backdrop-blur-sm"
          onClick={() => setShowGraph(false)}
        >
          <div
            className="surface-stone moss-edges relative w-full max-w-xl border border-stone-deep/40 p-8 text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <Glyph variant="node" className="mx-auto h-10 w-10 text-engraved" />
            <h3 className="mt-4 font-serif text-2xl text-engraved">Subgraph view</h3>
            <p className="mt-2 text-sm italic text-engraved/80">
              The fragment of the graph this answer was drawn from. Coming soon.
            </p>
            <button
              onClick={() => setShowGraph(false)}
              className="mt-6 text-xs uppercase tracking-widest text-engraved hover:text-brass"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

const Ask = () => {
  const [params] = useSearchParams();
  const initial = params.get("q") ?? "";
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentInitial = useRef(false);
  const turnstileRef = useRef<TurnstileInstance | null>(null);
  const turnstileTokenRef = useRef<string | null>(null);

  const submit = async (q: string) => {
    if (!q.trim() || loading) return;
    const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", text: q.trim() };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    const token = turnstileTokenRef.current ?? undefined;
    try {
      const ans = await askRobin(q, { turnstileToken: token });
      setMessages((m) => [...m, { id: `r-${Date.now()}`, role: "robin", answer: ans }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { id: `e-${Date.now()}`, role: "error", text: robinVoiceForError(err) },
      ]);
    } finally {
      setLoading(false);
      // Tokens are single-use; request a fresh one for the next submission.
      turnstileTokenRef.current = null;
      turnstileRef.current?.reset();
    }
  };

  useEffect(() => {
    if (initial && !sentInitial.current) {
      sentInitial.current = true;
      submit(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const empty = messages.length === 0 && !loading;

  return (
    <div className="relative flex h-screen flex-col bg-background">
      <AmbientGlyphs />
      <div className="relative z-10 flex h-full flex-col">
        <SiteHeader />

        <main ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[720px] px-6 py-12">
            {empty && (
              <div className="animate-fade-in-up py-16 text-center">
                <Glyph variant="seal" className="mx-auto h-10 w-10 text-moss" />
                <h1 className="mt-6 font-serif text-5xl text-ink">Ask me about the world.</h1>
                <p className="mt-4 font-serif text-xl italic text-muted-foreground">
                  I'll read the stones.
                </p>
                <div className="mt-12 grid gap-2 text-left">
                  {[
                    "Who are the current Four Emperors?",
                    "What connects Nico Robin to the Void Century?",
                    "Which Marines have fought Luffy?",
                  ].map((s) => (
                    <button
                      key={s}
                      onClick={() => submit(s)}
                      className="group flex items-center gap-3 border border-border bg-secondary/60 px-4 py-3 text-left transition-all hover:border-moss/50 hover:bg-secondary"
                    >
                      <Glyph variant="dot" className="h-3 w-3 text-moss/70 group-hover:text-moss" />
                      <span className="font-serif text-base italic text-ink/80">"{s}"</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-10">
              {messages.map((m) => {
                if (m.role === "user") {
                  return (
                    <div key={m.id} className="flex justify-end animate-fade-in-up">
                      <div className="surface-stone moss-edges relative max-w-[85%] overflow-hidden rounded-sm border border-stone-deep/40 px-5 py-3">
                        <p className="font-sans text-[15px] leading-relaxed text-engraved">{m.text}</p>
                      </div>
                    </div>
                  );
                }
                if (m.role === "robin") return <RobinMessage key={m.id} answer={m.answer} />;
                return (
                  <div key={m.id} className="animate-fade-in-up">
                    <div className="mb-3 flex items-center gap-3">
                      <Glyph variant="seal" className="h-5 w-5 text-moss" />
                      <span className="font-serif text-lg italic text-moss">Robin</span>
                    </div>
                    <div className="surface-parchment relative rounded-sm border border-parchment-deep/60 px-7 py-5 shadow-soft">
                      <p className="pl-4 font-serif text-[16px] italic leading-relaxed text-ink/80">{m.text}</p>
                    </div>
                  </div>
                );
              })}
              {loading && <ReadingAnimation />}
            </div>
          </div>
        </main>

        <Turnstile
          ref={turnstileRef}
          siteKey={TURNSTILE_SITE_KEY}
          options={{ size: "invisible" }}
          onSuccess={(token) => {
            turnstileTokenRef.current = token;
          }}
          onError={() => {
            turnstileTokenRef.current = null;
          }}
          onExpire={() => {
            turnstileTokenRef.current = null;
            turnstileRef.current?.reset();
          }}
        />

        {/* Input */}
        <div className="border-t border-border bg-sky/80 backdrop-blur-md">
          <form
            onSubmit={(e) => { e.preventDefault(); submit(input); }}
            className="mx-auto flex w-full max-w-[720px] items-center gap-3 px-6 py-5"
          >
            <div className="flex flex-1 items-center gap-3 border border-border bg-card-foreground/95 px-4 py-3 shadow-soft transition-colors focus-within:border-moss/60">
              <Glyph variant="ask" className="h-4 w-4 shrink-0 text-moss/70" />
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask Robin about the One Piece world…"
                disabled={loading}
                className="flex-1 bg-transparent font-serif text-lg italic text-ink placeholder:text-ink/40 focus:outline-none disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Send"
              className="surface-stone group flex h-[52px] w-[52px] items-center justify-center border border-stone-deep/40 text-engraved transition-all hover:bg-stone-deep disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Glyph variant="seal" className="h-5 w-5 transition-transform group-hover:rotate-45" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Ask;
