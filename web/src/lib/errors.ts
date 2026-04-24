export class RateLimitError extends Error {
  retryAfter?: number;
  constructor(message: string, retryAfter?: number) {
    super(message);
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

export class TurnstileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TurnstileError";
  }
}

export class BackendError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "BackendError";
    this.status = status;
  }
}
