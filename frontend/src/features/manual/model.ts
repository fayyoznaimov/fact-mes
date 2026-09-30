export type Group = 'day' | 'shift' | 'loom';
export type ColumnKind = 'machine' | 'none' | 'power' | 'ticket';
export type Column = {id: string; name: string; kind: ColumnKind};
export type Cat = {n: number | null; min: number; avg_sec: number | null; pct: number; ticketed_min?: number};
export type ManualRow = {
  key: string; looms: number; shed_eff: number | null; time_eff: number; stop_pct: number;
  prod_eff: number; stop_min: number; explained_pct: number | null; cats: Record<string, Cat>;
};
export type ManualResponse = {
  from: string; to: string; group: Group;
  installed: number; days: number; shifts: number;
  columns: Column[]; rows: ManualRow[]; totals: ManualRow;
};

export function hms(s: number | null): string {
  if (s == null) return '—';
  const n = Math.round(s);
  const h = Math.floor(n / 3600), m = Math.floor(n % 3600 / 60), x = n % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`;
}

export function paintEff(v: number | null): string {
  if (v == null || isNaN(v)) return '';
  if (v >= 1 && v <= 69) return ' c-red';
  if (v >= 70 && v <= 79) return ' c-yel';
  return '';
}

export const GROUP_KEY_NAME: Record<Group, string> = {day: 'День', shift: 'Смена', loom: 'Станок'};

export function noneColClass(c: Column): string {
  return c.kind === 'none' ? ' none-col' : '';
}

export function isHotCell(c: Column, v: Cat | undefined): boolean {
  return !!v && c.kind === 'none' && v.pct > 5;
}

export function rowKeyLabel(row: ManualRow, group: Group, fday: (v: unknown) => string): string {
  return group === 'day' ? fday(row.key) : row.key;
}

export function unexplainedMinutes(totals: ManualRow): number {
  return totals.cats.unexplained?.min ?? 0;
}
