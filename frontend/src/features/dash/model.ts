export type DashTotals = {
  running: number; stopped: number; with_ticket: number; kpicks: number;
  weft_ct: number; warp_ct: number; top_ct: number;
  with_plan: number; looms: number; with_product: number; with_operator: number;
};
export type Mismatch = {loom: string; text: string};
export type DashOperator = {name: string; code: string};
export type DashTicket = {reason: string};
export type DashRow = {
  loom: string; state: string; state_min?: number; reason?: string; cause_ru?: string;
  ticket?: DashTicket | null;
  rpm_now?: number | null; rpm_shift?: number | null;
  article_from?: string; order_no?: string; design?: string; client?: string; plan_product?: string;
  article?: string; candidates?: string[];
  kpicks: number; towels: number; effic?: number | null;
  operator?: DashOperator | null;
  weft_ct: number; warp_ct: number; top_ct: number; manual_ct?: number;
  mismatch?: string[]; notes?: string[];
  size?: string; gsm?: number | string; cloth?: string; meters?: number; pieces?: number; panels?: number;
  weft_fix_min?: number; warp_fix_min?: number; top_fix_min?: number;
  yarn?: Record<string, string>; lots?: Record<string, string>;
};
export type DashResponse = {
  totals: DashTotals; mismatches: Mismatch[]; rows: DashRow[]; articles: string[]; yarn_titles: Record<string, string>;
};
export type ForecastEvent = {at: string; when?: string; in_min: number; loom: string; what: string};
export type ForecastResponse = {events?: ForecastEvent[]; stale?: boolean; snapshot_at?: string};

export type ShowOnly = 'all' | 'stop' | 'ticket';

export const dur = (sec: number): string => {
  sec = Math.max(0, sec | 0);
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60);
  return h ? `${h} ч ${String(m).padStart(2, '0')} мин` : `${m} мин`;
};

export function filterRows(rows: DashRow[], only: ShowOnly): DashRow[] {
  return rows.filter(r => only === 'all' ? true : only === 'stop' ? r.state === 'stop' : !!r.ticket);
}

export function noteText(t: DashTotals): string {
  return `По плану цеха на этот день — ${t.with_plan} станков из ${t.looms}, изделие 1С выбрано у ${t.with_product}`
    + (t.with_plan > t.with_product ? ` (у остальных заказ не пришёл из 1С или изделие не выбрано во вкладке «План»)` : '')
    + `. Оператор назначен у ${t.with_operator}.`;
}

export function warnSummary(mismatches: Mismatch[]): string {
  return `На станке не то, что в плане: ${mismatches.length} — проверьте код ткани на станке или план`;
}

export function yarnEntries(row: DashRow, yarnTitles: Record<string, string>): {label: string; text: string}[] {
  return Object.entries(row.yarn || {}).map(([slot, v]) => ({
    label: yarnTitles[slot] || slot,
    text: v + ((row.lots || {})[slot] ? ' л.' + (row.lots || {})[slot] : ''),
  }));
}

export function articleOptions(row: DashRow, allArticles: string[]): {value: string; label: string; starred: boolean}[] {
  const all = new Set([...(row.candidates || []), ...allArticles]);
  return [{value: '', label: '— не задано —', starred: false},
    ...[...all].sort().map(a => ({value: a, label: a, starred: (row.candidates || []).includes(a)}))];
}

export function splitForecast(events: ForecastEvent[]): {soon: ForecastEvent[]; later: ForecastEvent[]} {
  const sorted = events.slice().sort((a, b) => a.in_min - b.in_min);
  return {soon: sorted.filter(e => e.in_min <= 120), later: sorted.filter(e => e.in_min > 120)};
}

export function inText(minutes: number): string {
  return minutes >= 60 ? `${Math.floor(minutes / 60)} ч ${minutes % 60} мин` : `${minutes} мин`;
}
