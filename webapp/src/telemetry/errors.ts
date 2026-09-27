import { api, ApiError, type ApiClient } from "@/api";

/**
 * Mini App JavaScript error reporting (#180): unhandled errors and promise rejections reach
 * `POST /app/api/client-error` instead of vanishing on the user's phone. Sampled per page load,
 * deduplicated and capped, so a crash loop costs a handful of requests. The server keeps a
 * closed, bounded set of fields (services/client_errors.py); see docs/observability.md.
 */

export type ClientErrorKind = "error" | "unhandledrejection";

export interface ClientErrorReport {
  kind: ClientErrorKind;
  message: string;
  source?: string;
  line?: number;
  col?: number;
  stack?: string;
  screen?: string;
}

/** Share of page loads that report at all: the whole session is in or out. */
export const ERROR_SAMPLE_RATE = 0.5;
/** Reports per page load, after deduplication. */
export const MAX_REPORTS_PER_PAGE = 3;
const MAX_MESSAGE = 300;
const MAX_STACK = 1200;

export interface ErrorReportingOptions {
  client?: ApiClient;
  /** Current screen (tab id), attached to each report. */
  screen?: () => string | undefined;
  sampleRate?: number;
  random?: () => number;
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
  /** Scripts outside this origin (Telegram's SDK, extensions) are not ours to report. */
  origin?: string;
}

const clip = (text: string, limit: number): string => (text.length > limit ? text.slice(0, limit) : text);
/** Query strings and fragments can carry data (even initData): keep only the path. */
const stripUrlTails = (text: string): string => text.replace(/[?#][^\s)]*/g, "");

function describe(value: unknown): { message: string; stack?: string } | null {
  if (value instanceof Error) {
    return { message: `${value.name}: ${value.message}`, stack: value.stack };
  }
  if (typeof value === "string") return { message: value };
  return null;
}

/** Pure: the report for an `error` event, or null when it is not ours or carries nothing. */
export function reportFromErrorEvent(event: ErrorEvent, origin?: string): ClientErrorReport | null {
  // "Script error." with no location is an opaque cross-origin error: nothing to act on.
  if (!event.filename && !event.error) return null;
  if (origin && event.filename && !event.filename.startsWith(origin)) return null;
  const described = describe(event.error) ?? (event.message ? { message: event.message } : null);
  if (!described) return null;
  return {
    kind: "error",
    message: described.message,
    ...(event.filename ? { source: event.filename } : {}),
    ...(event.lineno ? { line: event.lineno } : {}),
    ...(event.colno ? { col: event.colno } : {}),
    ...(described.stack ? { stack: described.stack } : {}),
  };
}

/** Pure: the report for an unhandled rejection, or null for API failures the server already logs. */
export function reportFromRejection(reason: unknown): ClientErrorReport | null {
  if (reason instanceof ApiError) return null;
  const described = describe(reason);
  if (!described) return null;
  return { kind: "unhandledrejection", ...described };
}

function bounded(report: ClientErrorReport, screen?: string): ClientErrorReport {
  return {
    ...report,
    message: clip(stripUrlTails(report.message), MAX_MESSAGE),
    ...(report.source ? { source: stripUrlTails(report.source) } : {}),
    ...(report.stack ? { stack: clip(stripUrlTails(report.stack), MAX_STACK) } : {}),
    ...(screen ? { screen } : {}),
  };
}

/**
 * Installs the global handlers. Returns the uninstall function (tests, hot reload).
 * Reporting never throws and never reports its own failures.
 */
export function installErrorReporting(options: ErrorReportingOptions = {}): () => void {
  const target = options.target ?? (typeof window !== "undefined" ? window : undefined);
  if (!target) return () => {};
  const random = options.random ?? Math.random;
  if (random() >= (options.sampleRate ?? ERROR_SAMPLE_RATE)) return () => {};

  const client = options.client ?? api;
  const origin = options.origin ?? (typeof location !== "undefined" ? location.origin : undefined);
  const seen = new Set<string>();
  let sent = 0;

  const send = (report: ClientErrorReport | null): void => {
    if (!report || sent >= MAX_REPORTS_PER_PAGE) return;
    const key = `${report.kind}|${report.message}|${report.source ?? ""}|${report.line ?? ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    sent++;
    let screen: string | undefined;
    try {
      screen = options.screen?.();
    } catch {
      screen = undefined;
    }
    const body = bounded(report, screen) as unknown as Record<string, unknown>;
    void client.request("/client-error", { method: "POST", body, keepalive: true }).catch(() => undefined);
  };

  const onError = (event: Event): void => send(reportFromErrorEvent(event as ErrorEvent, origin));
  const onRejection = (event: Event): void =>
    send(reportFromRejection((event as PromiseRejectionEvent).reason));

  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}
