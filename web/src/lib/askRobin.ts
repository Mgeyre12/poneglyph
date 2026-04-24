import { API_BASE_URL } from "./config";
import { BackendError, RateLimitError, TurnstileError } from "./errors";

export type Citation = { chapter: number; title: string };

export type RobinAnswer = {
  text: string;
  citations: Citation[];
};

export type AskOptions = {
  turnstileToken?: string;
  sessionId?: string;
  signal?: AbortSignal;
};

/**
 * Sends a question to /api/ask (SSE) and resolves with the full answer once
 * the `done` event arrives. v1 is a blocking call — streaming display is
 * Week 11 work. Any backend `error` event or HTTP failure rejects with a
 * typed error from ./errors.
 */
export async function askRobin(
  question: string,
  opts: AskOptions = {},
): Promise<RobinAnswer> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({
        question,
        session_id: opts.sessionId,
        turnstile_token: opts.turnstileToken,
      }),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new BackendError(
      err instanceof Error ? err.message : "Network error",
    );
  }

  if (!response.ok) {
    throw await httpErrorFor(response);
  }
  if (!response.body) {
    throw new BackendError("Empty response body from /api/ask");
  }

  return await consumeSSE(response.body);
}

async function httpErrorFor(response: Response): Promise<Error> {
  const payload = await safeReadJson(response);
  const detail =
    payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail: unknown }).detail
      : undefined;
  const detailMsg = extractDetailMessage(detail) ?? response.statusText;

  if (response.status === 429) {
    const retryAfter =
      numericDetail(detail, "retry_after") ??
      parseRetryAfter(response.headers.get("Retry-After"));
    return new RateLimitError(detailMsg, retryAfter);
  }
  if (response.status === 403) {
    return new TurnstileError(detailMsg);
  }
  return new BackendError(detailMsg, response.status);
}

async function safeReadJson(response: Response): Promise<unknown | null> {
  try {
    return await response.clone().json();
  } catch {
    return null;
  }
}

function extractDetailMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const m = (detail as { message: unknown }).message;
    if (typeof m === "string") return m;
  }
  return undefined;
}

function numericDetail(detail: unknown, key: string): number | undefined {
  if (detail && typeof detail === "object" && key in detail) {
    const v = (detail as Record<string, unknown>)[key];
    if (typeof v === "number") return v;
  }
  return undefined;
}

function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined;
  const n = Number(header);
  return Number.isFinite(n) ? n : undefined;
}

type SSEEvent = { event: string; data: string };

async function consumeSSE(
  body: ReadableStream<Uint8Array>,
): Promise<RobinAnswer> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const textChunks: string[] = [];
  let citations: Citation[] = [];
  let doneSeen = false;

  try {
    while (!doneSeen) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSSEBlock(rawEvent);
        if (parsed) {
          const handled = handleEvent(parsed, textChunks, (c) => (citations = c));
          if (handled === "done") {
            doneSeen = true;
            break;
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!doneSeen) {
    throw new BackendError("Stream ended before `done` event");
  }
  return { text: textChunks.join(""), citations };
}

function parseSSEBlock(raw: string): SSEEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value =
      colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n") };
}

function handleEvent(
  evt: SSEEvent,
  textChunks: string[],
  setCitations: (c: Citation[]) => void,
): "done" | "continue" {
  if (evt.event === "answer_chunk") {
    const parsed = tryParse(evt.data);
    if (parsed && typeof parsed.text === "string") textChunks.push(parsed.text);
    return "continue";
  }
  if (evt.event === "done") {
    const parsed = tryParse(evt.data);
    if (parsed && Array.isArray(parsed.citations)) {
      setCitations(parsed.citations.filter(isCitation));
    }
    return "done";
  }
  if (evt.event === "error") {
    const parsed = tryParse(evt.data);
    const code =
      parsed && typeof parsed.code === "string" ? parsed.code : "backend_error";
    const message =
      parsed && typeof parsed.message === "string"
        ? parsed.message
        : "Unknown backend error";
    throw errorForSSECode(code, message);
  }
  // step_start / step_complete / unknown — ignored for v1 blocking call
  return "continue";
}

function tryParse(data: string): any {
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}

function isCitation(c: unknown): c is Citation {
  return (
    !!c &&
    typeof c === "object" &&
    typeof (c as Citation).chapter === "number" &&
    typeof (c as Citation).title === "string"
  );
}

function errorForSSECode(code: string, message: string): Error {
  if (code === "rate_limit_exceeded") return new RateLimitError(message);
  if (code.startsWith("turnstile")) return new TurnstileError(message);
  return new BackendError(message);
}
