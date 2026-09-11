/**
 * Pure gameplay calculation utilities.
 * Exactly matches and types the logic tested in tests/client.test.cjs.
 */

export interface SquareSymbols {
  correct: string;
  wrong: string;
  unused: string;
}

export function squares(
  used: number,
  max: number,
  solved: boolean,
  symbols: SquareSymbols
): string {
  const wrong = solved ? Math.max(used - 1, 0) : used;
  return (
    symbols.wrong.repeat(wrong) +
    (solved ? symbols.correct : "") +
    symbols.unused.repeat(Math.max(max - wrong - (solved ? 1 : 0), 0))
  );
}

export interface HistogramRowInput {
  attempts: number;
  count?: number;
}

export interface HistogramRowOutput {
  attempts: number;
  count: number;
  best: boolean;
  width: number;
}

export interface HistogramResult {
  played: number;
  rows: HistogramRowOutput[];
}

export function histogram(
  distribution?: HistogramRowInput[] | null
): HistogramResult {
  const rows = distribution || [];
  const played = rows.reduce((sum, row) => sum + (row.count || 0), 0);
  const max = Math.max(1, ...rows.map((row) => row.count || 0));

  return {
    played,
    rows: rows.map((row) => ({
      attempts: row.attempts,
      count: row.count || 0,
      best: (row.count || 0) > 0 && row.count === max,
      width: Math.max(8, Math.round((100 * (row.count || 0)) / max)),
    })),
  };
}

export interface TrophyPlacement {
  position: number;
}

export function cabinetCounts(
  all?: TrophyPlacement[] | null
): [number, number, number] {
  return [1, 2, 3].map(
    (position) => (all || []).filter((tag) => tag.position === position).length
  ) as [number, number, number];
}

export function mergeProfile<T extends Record<string, any>>(
  previous: T,
  incoming: Partial<T>,
  lightweight: boolean
): T {
  return lightweight ? Object.assign({}, previous, incoming) : (incoming as T);
}
