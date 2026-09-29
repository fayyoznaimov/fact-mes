export type ScheduleShift = {shift: string; start: string; end: string; off?: boolean};
export type PlanBar = {order_no?: string; product_code?: string; product?: string; design?: string;
  note?: string; start: string; end: string; days: number; qty_plan?: number | null};
export type FactBar = {start: string; end: string; shift: string; cloth?: string; towels: number;
  eff: number; run_min: number; idle?: boolean};
export type GanttLoom = {loom: string; group: string; plan: PlanBar[]; fact: FactBar[]};
export type GanttData = {
  from: string; to: string; days: string[]; now: string; last_fact_day: string | null;
  schedule: ScheduleShift[]; looms: GanttLoom[];
};

export const CAUSE_COLOR: Record<string, string> = {
  Weft: '#df5656', Warp: '#d99829', Warp_top: '#b983db', Manual: '#5f8bd1', Power_off: '#59626d', Other: '#bd737c',
};
const WEEKDAYS = 'вс пн вт ср чт пт сб'.split(' ');

export function timeScale(from: string, to: string) {
  const t0 = Date.parse(from), span = Date.parse(to) - t0;
  const pos = (t: string) => Math.max(0, Math.min(100, (Date.parse(t) - t0) / span * 100));
  const wid = (a: string, b: string) => Math.max(0.2, pos(b) - pos(a));
  return {t0, span, pos, wid};
}

export const hueOf = (s: string) => { let h = 0; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };

export function planBarView(b: PlanBar, dmy: (d: string) => string, nf: (x: unknown, d?: number) => string) {
  const what = b.order_no ? `${b.order_no} ${b.design || b.product || ''}` : (b.note || b.product || '');
  const tip = [b.order_no ? 'заказ ' + b.order_no : '', b.product_code || b.product || '', b.note || '',
    `с ${dmy(b.start)}, ${b.days} дн.`, b.qty_plan ? `план ≈ ${nf(b.qty_plan)} шт` : ''].filter(Boolean).join('; ');
  const label = what + (b.qty_plan ? ` · ≈${nf(b.qty_plan)}` : '');
  return {what, tip, label, hasOrder: !!b.order_no, hue: b.order_no ? hueOf(b.order_no) : null};
}

export function factBarView(f: FactBar, dmy: (d: string) => string, nf: (x: unknown, d?: number) => string) {
  const cls = f.idle ? 'idle' : f.eff < 70 ? 'e-red' : f.eff < 80 ? 'e-yel' : 'e-ok';
  const tip = `смена ${f.shift} ${dmy(f.start)}: ${f.cloth || 'код ткани не задан'}; ${nf(f.towels)} шт; КПД ${nf(f.eff, 1)} %; работал ${f.run_min} мин. Щелчок — остановы`;
  const label = f.idle ? 'стоял' : `${nf(f.towels)} шт ${nf(f.eff, 0)}%`;
  return {cls, tip, label};
}

export function rangeText(g: GanttData, dmy: (d: string) => string): string {
  return `${dmy(g.from)} 07:00 — ${dmy(g.to)} 07:00; факт по ${g.last_fact_day ? dmy(g.last_fact_day) : '—'}`;
}

export function weekdayOf(day: string): string {
  return WEEKDAYS[new Date(day.replace(/\./g, '-') + 'T12:00').getDay()];
}

export function lastWorkedFact(loom: GanttLoom): FactBar | undefined {
  const worked = loom.fact.filter(x => !x.idle);
  return worked[worked.length - 1];
}

// --- Диалог остановов ---
export type StopEvent = {start: string; at?: string; dur: number; dur_in?: number; cause: string; cause_ru: string; code?: string; resp?: number | null};
export type CauseTotal = {cause: string; cause_ru: string; n: number; sec: number};
export type ShiftInfo = {id: string; effic: number; run_min: number; stop_min: number; cloth?: string; worked: boolean} | null;
export type TimelineData = {loom: string; from: string; to: string; events: StopEvent[]; by_cause: CauseTotal[]; stop_sec: number; shift: ShiftInfo};

export function timelineTitle(loom: string, d: TimelineData, dmy: (day: string) => string): string {
  const sh = d.shift;
  return `${loom}: ${sh ? 'смена ' + sh.id.slice(11) + ', ' : ''}${dmy(d.from)} ${d.from.slice(11, 16)}–${d.to.slice(11, 16)}`;
}
export function timelineSummary(d: TimelineData, nf: (x: unknown, dg?: number) => string): string {
  const sh = d.shift;
  return (sh ? `КПД ${nf(sh.effic, 1)} %, работал ${sh.run_min} мин, стоял ${sh.stop_min} мин; ` : '')
    + `остановов ${d.events.length}, ${nf(d.stop_sec / 60, 0)} мин${sh && sh.cloth ? '; ткань ' + sh.cloth : ''}`;
}
export function eventBarView(e: StopEvent, t0: number, span: number) {
  const left = (Date.parse(e.at || e.start) - t0) / span * 100;
  const width = Math.max(0.12, (e.dur_in ?? e.dur) * 1000 / span * 100);
  const color = CAUSE_COLOR[e.cause] || CAUSE_COLOR.Other;
  return {left, width, color};
}
export function tickLabels(t0: number, span: number): {left: number; text: string}[] {
  const ticks: {left: number; text: string}[] = [];
  for (let t = Math.ceil(t0 / 3600e3) * 3600e3; t <= t0 + span; t += 3600e3)
    ticks.push({left: (t - t0) / span * 100, text: String(new Date(t).getHours()).padStart(2, '0') + ':00'});
  return ticks;
}
export function eventRowStart(e: StopEvent, from: string, dmy: (day: string) => string): string {
  return (e.start < from ? dmy(e.start) + ' ' : '') + e.start.slice(11, 19);
}

// --- Даты периода (те же вычисления, что у легаси gtAdd/gtMonday/gtIso) ---
export const ymd = (t: Date) => t.getFullYear() + '.' + String(t.getMonth() + 1).padStart(2, '0') + '.' + String(t.getDate()).padStart(2, '0');
export const addDays = (d: string, n: number) => {
  const t = new Date(d.replace(/\./g, '-') + 'T12:00'); t.setDate(t.getDate() + n); return ymd(t);
};
export const monday = () => { const t = new Date(); t.setDate(t.getDate() - (t.getDay() + 6) % 7); return ymd(t); };
export const isoOf = (t: Date) => `${ymd(t).replace(/\./g, '-')}T${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}:00`;
