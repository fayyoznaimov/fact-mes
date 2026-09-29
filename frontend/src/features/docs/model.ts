import { nf } from '../report/model';

export type DocKind = 'setup' | 'payroll' | 'report' | 'rate';
export type ChipKind = '' | DocKind | 'log';

export type DocKindInfo = {id: string; title: string; can_post: boolean};

export type DocListItem = {
  id: number; number: string; status: 'posted' | 'cancelled'; type: string; title: string;
  created_at: string; created_by: string; summary?: Record<string, unknown>; warnings_count?: number; search?: string;
};

export type DiffField = {
  label?: string; title?: string; field?: string; loom?: string;
  before: unknown; after: unknown;
  before_source?: string; after_source?: string;
  changed?: boolean; delta?: number | null;
};

export type LogItem = {object: string; entity_text: string; action: string; action_text: string; fields: DiffField[]};
export type LogOperation = {at: string; actor: string; items: LogItem[]};

export type SetupLoomVersion = {
  loom: string; version: number; valid_from: string; context?: Record<string, string>;
  fields: DiffField[]; warning?: string;
  previous?: {created_at: string; author: string} | null;
};

export type DocFull = {
  id: number; number: string; status: 'posted' | 'cancelled'; type: string; title: string; type_title: string;
  created_by: string; created_at: string;
  period_from?: string | null; period_to?: string | null; comment?: string | null;
  cancelled_by?: string; cancelled_at?: string; cancel_reason?: string;
  supersedes?: {id: number; number: string; created_at: string} | null;
  replaced_by: {id: number; number: string}[];
  warnings: string[];
  history: {at: string; actor: string; action: string; text?: string}[];
  summary?: Record<string, unknown>;
  changes?: DiffField[];
  result?: Record<string, unknown>;
  looms?: SetupLoomVersion[];
};

export type DocTab = 'content' | 'changes' | 'warnings' | 'history';

export const dxDay = (v: unknown): string => v ? String(v).replace(/^(\d{4})[-.](\d\d)[-.](\d\d).*$/, '$3.$2.$1') : '';
export const dxTime = (v: unknown): string => v ? String(v).replace(/^(\d{4})[-.](\d\d)[-.](\d\d)[T ](\d\d:\d\d).*$/, '$3.$2.$1 $4') : '—';
export const dxNum = (v: unknown): string => typeof v === 'number'
  ? v.toLocaleString(document.documentElement.lang === 'en' ? 'en-GB' : 'ru-RU', {maximumFractionDigits: Math.abs(v) < 10 ? 4 : 1})
  : String(v ?? '');
export const docMoney = (v: unknown): string => nf(Math.round(Number(v) || 0));

export function dxObjects(n: number): string {
  const word = n % 10 === 1 && n % 100 !== 11 ? 'объект' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'объекта' : 'объектов';
  return `${n} ${word}`;
}

export function dxGroup<T extends Record<string, unknown>>(rows: T[], key: string): [unknown, T[]][] {
  const m = new Map<unknown, T[]>();
  rows.forEach(r => { if (!m.has(r[key])) m.set(r[key], []); m.get(r[key])!.push(r); });
  return [...m];
}

export function dxCtx(ctx: Record<string, string> | undefined): [string, string][] {
  return ctx && Object.keys(ctx).length ? Object.entries(ctx) : [];
}

export type DiffCell = {text: string; empty: boolean; source?: string};
export function dxVal(v: unknown, src?: string): DiffCell {
  return {text: v == null || v === '' ? 'пусто' : dxNum(v), empty: v == null || v === '', source: src};
}
export type DiffDelta = {sign: '+' | '−'; text: string} | null;
export function dxDelta(d: number | null | undefined): DiffDelta {
  if (d == null || d === 0 || isNaN(d)) return null;
  return {sign: d > 0 ? '+' : '−', text: dxNum(Math.abs(Math.round(d * 1000) / 1000))};
}

export type DiffRowView = {
  key: string; label: string; kind: 'same' | 'add' | 'del' | 'chg';
  before: DiffCell; after: DiffCell; delta: DiffDelta;
};
export function diffRows(fields: DiffField[], only = false): {rows: DiffRowView[]; hiddenCount: number} {
  const shown = only ? fields.filter(r => r.changed !== false) : fields;
  const hiddenCount = fields.length - shown.length;
  const rows = shown.map((r, i) => {
    const kind: DiffRowView['kind'] = r.changed === false ? 'same'
      : (r.before == null || r.before === '') && r.after != null && r.after !== '' ? 'add'
      : (r.after == null || r.after === '') && r.before != null && r.before !== '' ? 'del' : 'chg';
    return {
      key: String(r.field ?? r.label ?? r.title ?? i), label: String(r.label ?? r.title ?? r.field ?? ''),
      kind,
      before: kind === 'add' ? {text: 'не было', empty: true} : dxVal(r.before, r.before_source),
      after: kind === 'del' ? {text: 'удалено', empty: true} : dxVal(r.after, r.after_source),
      delta: dxDelta(r.delta),
    };
  });
  return {rows, hiddenCount};
}

export function moneyDiffFields(rows: {title: string; before: number | null; after: number | null}[]): DiffField[] {
  return rows.map(x => ({label: x.title, before: x.before, after: x.after, changed: true,
    delta: x.before != null && x.after != null ? x.after - x.before : null}));
}

// Переиспользуется и для ставки, и для отчёта: подставляет label из title и считает
// числовую разницу, если оба значения — числа.
export function titledDiffFields(changes: DiffField[]): DiffField[] {
  return changes.map(x => ({...x, label: x.title,
    delta: typeof x.before === 'number' && typeof x.after === 'number' ? x.after - x.before : null}));
}

export const docStatusText = (s: string): string => s === 'posted' ? 'проведён' : 'отменён';

export type Tile = {label: string; value: string; unit?: string};
export function docTiles(type: string, summary: Record<string, unknown> | undefined): Tile[] {
  const s = summary || {};
  if (type === 'setup') return [
    {label: 'Станков', value: String(s.looms ?? '')}, {label: 'С изменениями', value: String(s.changed_looms ?? '')},
    {label: 'Реквизитов меняется', value: String(s.changed_fields ?? '')}];
  if (type === 'rate') return [{label: 'Ставка', value: nf(s.rate as number, 2), unit: 'сум'},
    {label: 'Действует с', value: dxDay(s.valid_from)}];
  if (type === 'payroll') return [
    {label: 'К выплате', value: docMoney(s.salary), unit: 'сум'}, {label: 'Сотрудников', value: String(s.operators ?? '')},
    {label: 'Смен', value: String(s.shifts ?? '')}, {label: 'Не распределено', value: docMoney(s.unassigned_salary), unit: 'сум'}];
  if (type === 'report') return [
    {label: 'Станков', value: String(s.looms ?? '')}, {label: 'Дней', value: String(s.days ?? '')},
    {label: 'КПД', value: s.effic == null ? '—' : nf(s.effic as number, 1), unit: s.effic == null ? undefined : '%'},
    {label: 'Полотенца', value: nf(s.towels as number)}, {label: 'Кг', value: nf(s.kg as number, 1)}];
  return [];
}

export function dxSummary(d: DocListItem): string {
  const s = d.summary || {};
  if (d.type === 'payroll') return `к выплате ${nf(s.salary as number)} сум`;
  if (d.type === 'setup') return `станков: ${s.looms || 0}, реквизитов: ${s.changed_fields || 0}`;
  if (d.type === 'rate') return `${nf(s.rate as number, 2)} сум`;
  if (d.type === 'report') return `полотенец ${nf(s.towels as number)}, КПД ${nf(s.effic as number, 1)} %`;
  return '';
}

export function dxChanges(d: DocFull): number {
  if (d.type === 'setup') return (d.looms || []).reduce((a, l) => a + l.fields.filter(f => f.changed).length, 0);
  return (d.changes || []).length;
}

export type PayrollOperator = {operator_id: number; code: string; name: string; shifts: number; kpicks: number; salary: number};
export type PayrollShift = {day: string; shift: string; rate: number; unit: string; operators: {operator_id: number; looms?: string[]; kpicks: number; salary: number}[]};
export type PayrollResult = {operators?: PayrollOperator[]; shifts?: PayrollShift[]};

export function payrollLines(shifts: PayrollShift[], operatorId: number) {
  return shifts.flatMap(s => s.operators.filter(o => o.operator_id === operatorId)
    .map(o => ({...o, day: s.day, shift: s.shift, rate: s.rate, unit: s.unit})));
}

export function payrollUnassigned(shifts: PayrollShift[]): {day: string; shift: string; unassigned_salary: number}[] {
  return (shifts as (PayrollShift & {unassigned_salary?: number})[]).filter(s => (s.unassigned_salary || 0) > 0)
    .map(s => ({day: s.day, shift: s.shift, unassigned_salary: s.unassigned_salary || 0}));
}
