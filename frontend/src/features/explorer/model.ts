export type ExplorerTotals = {eff: number; run_h: number; stop_h: number; mpicks: number; rows: number; idle_shifts: number};
export type ExplorerLoomRow = {
  loom: string; eff: number; kpicks: number; weft_ct: number; weft_cmpx: number; warp_ct: number; top_ct: number;
  manual_ct: number; manual_h: number; wait_h: number; shifts: number; idle_shifts: number;
  warp_out_h: number; other_h: number; power_h: number;
};
export type ExplorerResponse = {
  totals: ExplorerTotals; causes: Record<string, number>; by_loom: ExplorerLoomRow[];
};
export type Group = 'all' | 'D' | 'J';

const CAUSE_COLOR: Record<string, string> = {
  Weft: '#df5656', Warp: '#d99829', Warp_top: '#b983db', Manual: '#5f8bd1', Power_off: '#59626d', Other: '#bd737c',
};
const EX_CAUSE: Record<string, string> = {
  'Уток': 'Weft', 'Основа': 'Warp', 'Верхний навой': 'Warp_top', 'Ручные остановы': 'Manual',
  'Питание выключено': 'Power_off', 'Прочее': 'Other',
};
const EX_EXTRA: Record<string, string> = {'Сход навоя': '#3f9c96', 'Съём ткани': '#8e9a3a'};

export function causeColor(name: string): string {
  return EX_EXTRA[name] || CAUSE_COLOR[EX_CAUSE[name]] || CAUSE_COLOR.Other;
}

export function sortedCauses(causes: Record<string, number>): [string, number][] {
  return Object.entries(causes).sort((a, b) => b[1] - a[1]);
}

export function causeShare(causes: [string, number][]): {name: string; hours: number; pct: number}[] {
  const sum = causes.reduce((s, [, h]) => s + h, 0) || 1;
  return causes.map(([name, hours]) => ({name, hours, pct: 100 * hours / sum}));
}

export function orderRange(a: string, b: string): [string, string] {
  return a <= b ? [a, b] : [b, a];
}

export function defaultRange(days: string[]): {from: string; to: string} {
  if (!days.length) return {from: '', to: ''};
  return {from: days[Math.min(days.length - 1, 29)] ?? days[days.length - 1], to: days[0]};
}

export function toggleShift(shifts: Set<string>, letter: string): Set<string> {
  if (shifts.has(letter) && shifts.size === 1) return shifts;
  const next = new Set(shifts);
  if (next.has(letter)) next.delete(letter); else next.add(letter);
  return next;
}

export function shiftsParam(shifts: Set<string>): string {
  return ['A', 'B', 'C'].filter(s => shifts.has(s)).join('');
}
