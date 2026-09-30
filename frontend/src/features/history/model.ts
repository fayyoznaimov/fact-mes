export type Period = 'day' | 'A' | 'B' | 'C';
export type SegmentKind = 'stop' | 'estimated_run' | 'unknown' | 'future' | 'observed_run' | 'observed_stop';
export type Segment = {start: number; end: number; kind: SegmentKind; cause?: string | null; reason?: string};
export type HistoryEvent = {
  start: number; end: number; cause: string; reason: string; code: string | null; shift: string | null;
  style: string | null; response_sec: number | null; duration_sec: number;
};
export type HistoryTicket = {id: number; start: number; end: number; open: boolean; reason: string; comment: string; cause: string | null};
export type ShiftCheck = {shift: string; run_min: number | null; stop_min: number | null; logged_stop_sec: number; can_estimate: boolean};
export type Totals = {stop: number; estimated_run: number; unknown: number; future: number; observed_run?: number; observed_stop?: number};
export type HistoryRow = {
  loom: string; events: HistoryEvent[]; segments: Segment[]; totals: Totals;
  shift_checks: ShiftCheck[]; invalid_records: number; overlap_sec: number; tickets: HistoryTicket[];
};
export type MachineHistory = {
  day: string; period: string; start: number; end: number; timezone: string; generated_at: number;
  catalog: string[]; available_from: string | null; available_to: string | null; rows: HistoryRow[];
};

export type SignalSample = {at: number; values: Record<string, unknown>};
export type SignalsResponse = {loom: string; start: number; end: number; samples: SignalSample[]; note: string};

const CAUSE_COLOR: Record<string, string> = {
  Weft: '#df5656', Warp: '#d99829', Warp_top: '#b983db', Manual: '#5f8bd1', Power_off: '#59626d', Other: '#bd737c',
};
export const MH_CAUSES: [string, string, string][] = ([['Weft', 'Уток'], ['Warp', 'Основа'], ['Warp_top', 'Ворс'],
  ['Manual', 'Ручной останов'], ['Other', 'Другие остановы']] as [string, string][])
  .map(([k, t]) => [k, CAUSE_COLOR[k], t]);
export const MH_SEGS: Record<string, [string, string]> = {
  estimated_run: ['#a3bfad', 'Работа · по сменным итогам'], observed_run: ['#c9d8ce', 'Работа · по снимкам FACT'],
  observed_stop: ['#59626d', 'Стоит · по снимкам FACT, в журнале остановов записи нет'], stop: ['#bd737c', ''],
};

export function mhColor(cause: string): string {
  return (MH_CAUSES.find(c => c[0] === cause) || MH_CAUSES[MH_CAUSES.length - 1])[1];
}

export function mhDuration(s: number): string {
  return `${Math.floor(s / 3600)} ч ${Math.floor(s % 3600 / 60)} мин ${Math.floor(s % 60)} с`;
}

export function mhTime(s: number, full = false): string {
  const d = new Date((s + 18000) * 1000).toISOString();
  return (full ? d.slice(8, 10) + '.' + d.slice(5, 7) + ' ' : '') + d.slice(11, 19);
}

export function mhSegTitle(s: {kind: string; reason?: string | null; start: number; end: number}): string {
  if (!s.kind.startsWith('observed')) return '';
  return `${s.kind === 'observed_run' ? 'Работа' : 'Стоит' + (s.reason ? ': ' + s.reason : '')} · по снимкам FACT · ${mhTime(s.start, true)} — ${mhTime(s.end, true)}`;
}

export function mhStop(t: Totals): number {
  return (t.stop || 0) + (t.observed_stop || 0);
}

export type Packed<T> = {k: string; i: number; start: number; end: number; n: number; sec: number; x: T};
export function mhPack<T extends {start: number; end: number; duration_sec?: number}>(
  items: T[], gap: number, key: (x: T) => string,
): Packed<T>[] {
  const out: Packed<T>[] = [];
  items.forEach((x, i) => {
    const k = key(x), last = out[out.length - 1];
    if (last && last.k === k && x.start - last.end < gap) {
      last.end = Math.max(last.end, x.end); last.n++; last.sec += x.duration_sec || 0;
    } else out.push({k, i, start: x.start, end: x.end, n: 1, sec: x.duration_sec || 0, x});
  });
  return out;
}

function escHtml(v: unknown): string {
  return String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c] as string));
}

export function buildGridHtml(mh: MachineHistory): string {
  const span = mh.end - mh.start;
  const pct = (s: number) => 100 * (s - mh.start) / span;
  const gap = span / 1000;
  const rect = (a: number, b: number, fill: string, extra = '', title = '') =>
    `<rect x="${pct(Math.max(mh.start, a))}" y="4" width="${Math.max(0, 100 * (Math.min(mh.end, b, mh.generated_at) - Math.max(mh.start, a)) / span)}" height="24" fill="${fill}" ${extra}>${title ? '<title>' + escHtml(title) + '</title>' : ''}</rect>`;
  const hours = span / 3600, step = hours === 24 ? 3 : 1;
  const ticks = Array.from({length: hours / step + 1}, (_, i) =>
    `<span style="left:${i * step / hours * 100}%">${i === hours / step && hours === 24 ? '24:00' : mhTime(mh.start + i * step * 3600).slice(0, 5)}</span>`).join('');
  const rowsHtml = mh.rows.map((r, ri) => {
    const segs = mhPack(r.segments.filter(s => s.kind !== 'future' && s.kind !== 'stop'), gap, s => s.kind + '|' + (s.cause || ''))
      .filter(p => p.k.startsWith('unknown') ? p.end - p.start >= gap : true)
      .map(p => rect(p.start, p.end, (MH_SEGS[p.x.kind] || [])[0] || `url(#mh-unknown-${ri})`, '', mhSegTitle({...p.x, start: p.start, end: p.end})))
      .join('');
    const events = mhPack(r.events, gap, e => e.cause).map(p =>
      rect(p.start, p.end, mhColor(p.x.cause), `data-event="${p.i}"`,
        p.n === 1 ? `${p.x.reason} · ${mhTime(p.start, true)} — ${mhTime(p.end, true)} · ${mhDuration(p.sec)}`
          : `${p.x.reason} ×${p.n} · ${mhTime(p.start, true)} — ${mhTime(p.end, true)} · всего ${mhDuration(p.sec)}`))
      .join('');
    const ticketsHtml = r.tickets.map((t, i) =>
      `<rect x="${pct(Math.max(mh.start, t.start))}" y="32" height="5" width="${Math.max(0, 100 * (Math.min(mh.end, t.end, mh.generated_at) - Math.max(mh.start, t.start)) / span)}" fill="#348ec1" data-ticket="${i}"><title>Тикет ${t.id}: ${escHtml(t.reason)}</title></rect>`)
      .join('');
    return `<div class="mh-row" data-row="${ri}"><button type="button" data-loom="${ri}" aria-label="История ${escHtml(r.loom)}">${escHtml(r.loom)}</button>`
      + `<svg viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="${escHtml(r.loom)}: ${r.events.length} остановов. Подробности по кнопке станка."><defs><pattern id="mh-unknown-${ri}" width="0.7" height="7" patternUnits="userSpaceOnUse"><rect width="0.7" height="7" fill="var(--surface-2)"/><path d="M0 7 L0.7 0" stroke="var(--rule)" stroke-width="0.16"/></pattern></defs>${segs}${events}${ticketsHtml}</svg>`
      + `<span class="mh-total">${Math.floor(mhStop(r.totals) / 3600)} ч ${Math.floor(mhStop(r.totals) % 3600 / 60)} мин</span></div>`;
  }).join('');
  return `<div class="mh-row mh-axis"><span>Станок</span><div class="mh-ticks">${ticks}</div><span class="mh-total">Простой</span></div>${rowsHtml}`;
}

export function statusText(mh: MachineHistory): string {
  const events = mh.rows.reduce((s, r) => s + r.events.length, 0);
  const unknown = mh.rows.filter(r => r.totals.unknown > 0).length;
  return `${mh.day} · Станки: ${mh.rows.length} · Остановки: ${events} · Журнал доступен по ${mh.available_to || '—'}. ${unknown ? 'Станки с промежутками без подтверждённого состояния: ' + unknown + '.' : ''}`;
}

export function loomGroups(catalog: string[]): string[] {
  return [...new Set(catalog.map(l => l.replace(/\d+$/, '')))];
}

export function loomsParam(selected: string, catalog: string[]): string {
  if (selected.startsWith('row:')) {
    const g = selected.slice(4);
    return catalog.filter(l => l.replace(/\d+$/, '') === g).join(',');
  }
  return selected;
}

export const EVENTS_PAGE_SIZE = 50;
export function pageEvents(events: HistoryEvent[], page: number): HistoryEvent[] {
  return events.slice(page * EVENTS_PAGE_SIZE, (page + 1) * EVENTS_PAGE_SIZE);
}
export function pageRangeText(total: number, page: number): string {
  return `${total ? page * EVENTS_PAGE_SIZE + 1 : 0}–${Math.min(total, (page + 1) * EVENTS_PAGE_SIZE)} из ${total}`;
}

export function flattenSignalValues(o: Record<string, unknown> | undefined, prefix = ''): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  Object.entries(o || {}).forEach(([k, v]) => {
    const key = prefix ? prefix + '.' + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flattenSignalValues(v as Record<string, unknown>, key));
    else out[key] = v;
  });
  return out;
}

export const SIGNAL_LABELS: Record<string, string> = {
  state: 'Состояние', state_sec: 'Длительность состояния, с', cause: 'Причина Toyota', running: 'Работает',
  rpm: 'RPM (исходное значение FACT)', effic_shift: 'Эффективность смены, %', effic_24h: 'Эффективность за 24 часа, %',
  stops_shift: 'Количество остановов за смену', stops_24h: 'Количество остановов за 24 часа',
  doff_min: 'Прогноз съёма ткани, мин', beam_out_min: 'Прогноз схода навоя, мин', top_beam_out_min: 'Прогноз схода верхнего навоя, мин',
  'details.remaining_m': 'Остаток основы, м', 'details.stop_time_sec': 'Текущий останов, с',
};

export type FlatSample = {at: number; flat: Record<string, unknown>};
export function signalKeys(samples: FlatSample[]): string[] {
  return [...new Set(samples.flatMap(s => Object.keys(s.flat)))].sort();
}

export type ChartPoint = {at: number; v: unknown};
export function chartValues(samples: FlatSample[], key: string): ChartPoint[] {
  return samples.map(s => ({at: key.startsWith('details.') ? Number(s.flat.details_at ?? s.at) : s.at, v: s.flat[key]}));
}

function isNumericPoint(v: unknown): boolean {
  return v !== null && v !== '' && Number.isFinite(Number(v));
}

export function chartPolylines(values: ChartPoint[], start: number, end: number): string[] {
  const numeric = values.filter(s => isNumericPoint(s.v));
  if (!numeric.length) return [];
  const lo = Math.min(...numeric.map(s => Number(s.v))), hi = Math.max(...numeric.map(s => Number(s.v))), span = hi - lo || 1;
  const chunks: string[][] = [];
  let chunk: string[] = [], prev: number | null = null;
  for (const s of values) {
    if (!isNumericPoint(s.v)) { if (chunk.length) chunks.push(chunk); chunk = []; prev = null; continue; }
    if (prev !== null && s.at - prev > 120) { chunks.push(chunk); chunk = []; }
    chunk.push(((s.at - start) / (end - start) * 1000).toFixed(2) + ',' + (150 - (Number(s.v) - lo) / span * 130).toFixed(2));
    prev = s.at;
  }
  if (chunk.length) chunks.push(chunk);
  return chunks.map(c => c.join(' '));
}

export function chartRange(values: ChartPoint[]): {lo: number; hi: number} | null {
  const numeric = values.filter(s => isNumericPoint(s.v)).map(s => Number(s.v));
  return numeric.length ? {lo: Math.min(...numeric), hi: Math.max(...numeric)} : null;
}
