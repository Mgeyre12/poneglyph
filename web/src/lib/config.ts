const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const rawTurnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY;

function required(name: string, value: string | undefined): string {
  if (!value || !value.trim()) {
    throw new Error(
      `Missing required env var ${name}. Copy web/.env.example to web/.env.local and fill it in.`,
    );
  }
  return value.trim().replace(/\/$/, "");
}

export const API_BASE_URL = required("VITE_API_BASE_URL", rawApiBaseUrl);
export const TURNSTILE_SITE_KEY = required(
  "VITE_TURNSTILE_SITE_KEY",
  rawTurnstileSiteKey,
);
