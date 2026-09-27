import { api, type ApiClient } from "@/api";

/**
 * Mini App startup timing (#32): how long the app takes to become usable on the phone,
 * reported once per page load to `POST /app/api/perf`. Numbers only — the server keeps a
 * closed set of bounded metrics (services/performance.py) and logs them without any id.
 * See docs/performance.md.
 */

export type StartupOutcome = "ok" | "error";

export interface StartupMetrics {
  ttfb_ms?: number;
  dom_ready_ms?: number;
  first_data_ms?: number;
  api_me_ms?: number;
  api_me_server_ms?: number;
  transfer_kb?: number;
}

type TimingSource = Pick<Performance, "now" | "getEntriesByType">;

const round = (value: number): number => Math.round(value * 10) / 10;

/** Pure: derives the metrics from the Performance timeline at the moment data is on screen. */
export function collectStartupMetrics(perf: TimingSource, firstDataAt: number): StartupMetrics {
  const metrics: StartupMetrics = { first_data_ms: round(firstDataAt) };
  const navigation = perf.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
  let transferBytes = 0;
  if (navigation) {
    if (navigation.responseStart > 0) metrics.ttfb_ms = round(navigation.responseStart);
    if (navigation.domContentLoadedEventEnd > 0) metrics.dom_ready_ms = round(navigation.domContentLoadedEventEnd);
    transferBytes += navigation.transferSize || 0;
  }
  const resources = perf.getEntriesByType("resource") as PerformanceResourceTiming[];
  for (const entry of resources) transferBytes += entry.transferSize || 0;
  const me = resources.find((entry) => /\/app\/api\/me$/.test(entry.name));
  if (me) {
    metrics.api_me_ms = round(me.duration);
    const server = (me.serverTiming || []).find((timing) => timing.name === "app");
    if (server) metrics.api_me_server_ms = round(server.duration);
  }
  if (transferBytes > 0) metrics.transfer_kb = round(transferBytes / 1024);
  return metrics;
}

let reported = false;

/** Sends the startup report once per page load. Never throws, never blocks the UI. */
export async function reportStartup(
  outcome: StartupOutcome,
  client: ApiClient = api,
  perf: TimingSource | undefined = typeof performance !== "undefined" ? performance : undefined,
): Promise<boolean> {
  if (reported || !perf) return false;
  reported = true;
  try {
    const metrics = collectStartupMetrics(perf, perf.now());
    await client.request("/perf", { method: "POST", body: { app: "v2", outcome, metrics }, keepalive: true });
    return true;
  } catch {
    return false;
  }
}

/** Test seam: allow another report in the same module instance. */
export function resetStartupReport(): void {
  reported = false;
}
