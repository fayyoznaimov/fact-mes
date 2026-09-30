export type Operator = {id: number; code: string; name: string; role: string; active: number | boolean};
export type Me = {role: string; employee_id: number | null} | null;

export type Doc = {
  status: string; foreman_id: number | null; note: string | null; source: string | null;
  updated_by: string | null; updated_at: string | null; confirmed_by: string | null; confirmed_at: string | null;
} | null;
export type AssignmentRow = {loom: string; operator_id: number | null};
export type ShiftDoc = {
  day: string; shift: string; hours: string; doc: Doc;
  assignments: AssignmentRow[]; masters: number[]; layout: Record<string, [number, number]>;
};
export type DocSummary = {
  day: string; shift: string; status: string; source: string | null;
  updated_by: string | null; confirmed_by: string | null;
  foreman_name: string | null; foreman_code: string | null;
  looms: number; operators: number; masters: number;
};

export const dash2dot = (v: string): string => (v || '').replace(/-/g, '.');
export const dot2dash = (v: string): string => (v || '').replace(/\./g, '-');

export function shiftNow(now: Date): {day: string; shift: string} {
  const d = new Date(now), h = d.getHours();
  const shift = h >= 7 && h < 15 ? 'A' : h >= 15 && h < 23 ? 'B' : 'C';
  if (h < 7) d.setDate(d.getDate() - 1);
  return {day: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`, shift};
}

export const opLabel = (o: Operator): string => `${o.name} (${o.code})`;

export function hueOf(s: string | number): number {
  let h = 0;
  for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

export function ownMasterOf(me: Me): number | null {
  return me?.role === 'master' ? me.employee_id : null;
}

export function isLocked(doc: Doc): boolean { return doc?.status === 'confirmed'; }

export function editableOperators(operators: Operator[], assignments: AssignmentRow[]): Operator[] {
  return operators.filter(o => o.role === 'operator' && (o.active || assignments.some(a => a.operator_id === o.id)));
}

export function searchOperators(operators: Operator[], search: string): Operator[] {
  const q = search.trim().toLocaleLowerCase();
  return operators.filter(o => o.role === 'operator' && o.active && `${o.code} ${o.name}`.toLocaleLowerCase().includes(q));
}

export function sortSuggestions(ops: Operator[], search: string): Operator[] {
  const s = search.trim();
  return [...ops].sort((a, b) => Number(String(b.code) === s) - Number(String(a.code) === s));
}

export function nextSuggestIndex(current: number, length: number, dir: 1 | -1): number {
  if (!length) return -1;
  return current < 0 ? (dir === 1 ? 0 : length - 1) : (current + dir + length) % length;
}

export function foremenOptions(operators: Operator[], selectedId: number | null): Operator[] {
  return operators.filter(o => o.role === 'foreman' && (o.active || o.id === selectedId));
}

export function mastersOptions(operators: Operator[], docMasters: number[]): Operator[] {
  return operators.filter(o => o.role === 'master' && (o.active || docMasters.includes(o.id)));
}

export function selectedMasters(ownMaster: number | null, locked: boolean, docMasters: number[]): number[] {
  return ownMaster && !locked ? [ownMaster] : docMasters;
}

export function toRows(assignments: Record<string, number | null>): AssignmentRow[] {
  return Object.entries(assignments).map(([loom, operator_id]) => ({loom, operator_id}));
}

export function byOperator(assignments: AssignmentRow[]): Record<number, string[]> {
  const by: Record<number, string[]> = {};
  assignments.forEach(a => { if (a.operator_id != null) (by[a.operator_id] ||= []).push(a.loom); });
  return by;
}

export type Summary = {total: number; withOperator: number; freeLooms: string[]; byOperator: {id: number; name: string; count: number}[]};
export function buildSummary(assignments: AssignmentRow[], operators: Operator[]): Summary {
  const by = byOperator(assignments);
  const freeLooms = assignments.filter(a => a.operator_id == null).map(a => a.loom);
  return {
    total: assignments.length, withOperator: assignments.length - freeLooms.length, freeLooms,
    byOperator: Object.entries(by).map(([id, looms]) => {
      const o = operators.find(x => x.id === +id);
      return {id: +id, name: o ? o.name : id, count: looms.length};
    }),
  };
}

export type MapLayout = {rows: number[]; colTrack: Record<number, number>; template: string; cells: {loom: string; row: number; col: number}[]};
export function mapLayout(layout: Record<string, [number, number]>, looms: string[]): MapLayout {
  const cells = looms.filter(l => layout[l]).map(l => ({loom: l, row: layout[l][0], col: layout[l][1]}));
  const rows = [...new Set(cells.map(c => c.row))].sort((a, b) => a - b);
  const cols = [...new Set(cells.map(c => c.col))].sort((a, b) => a - b);
  const colTrack: Record<number, number> = {};
  const tracks: string[] = [];
  cols.forEach((c, i) => {
    if (i && c - cols[i - 1] > 1) tracks.push('18px');
    tracks.push('minmax(92px,1fr)'); colTrack[c] = tracks.length;
  });
  return {rows, colTrack, template: tracks.join(' '), cells};
}

function escHtml(v: unknown): string {
  return String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c] as string));
}

export type PrintData = {
  day: string; shift: string; hours: string; doc: Doc;
  assignments: AssignmentRow[]; masters: number[]; foremanId: number | null; note: string;
  operators: Operator[];
};
export function buildPrintHtml(d: PrintData, fday: (v: unknown) => string, ftime: (v: unknown) => string): string {
  const person = (id: number | null) => { const o = d.operators.find(x => x.id === id); return o ? `${escHtml(o.name)} (${escHtml(o.code)})` : '—'; };
  const nameOf = (id: number) => d.operators.find(x => x.id === id)?.name || '';
  const by = byOperator(d.assignments);
  const rows = Object.entries(by).sort((a, b) => nameOf(+a[0]).localeCompare(nameOf(+b[0]), 'ru'))
    .map(([id, looms]) => `<tr><td>${person(+id)}</td><td>${escHtml(looms.join(', '))}</td><td class="n">${looms.length}</td><td class="sig"></td></tr>`).join('');
  const free = d.assignments.filter(a => a.operator_id == null).map(a => a.loom);
  return `<!doctype html><meta charset="utf-8"><title>Расстановка смены ${d.shift} · ${d.day}</title>
<style>body{font:13px/1.45 "IBM Plex Sans",Arial,sans-serif;margin:16mm 14mm;color:#000}
h1{font-size:18px;margin:0 0 10px}p{margin:4px 0}table{border-collapse:collapse;width:100%;margin-top:12px}
th,td{border:1px solid #555;padding:5px 7px;text-align:left;vertical-align:top}th{background:#eee}
td.n{text-align:right}td.sig{width:26%}.st{margin-top:12px;color:#333}
.signs{display:flex;justify-content:space-between;gap:20px;margin-top:30px}</style>
<h1>Расстановка смены ${d.shift} · ${fday(d.day)} · ${d.hours}</h1>
<p>Мастер смены: <b>${d.foremanId ? person(d.foremanId) : '—'}</b></p>
<p>Мастерицы: <b>${d.masters.map(person).join(', ') || '—'}</b></p>
<table><thead><tr><th>Оператор</th><th>Станки</th><th>Станков</th><th>Подпись</th></tr></thead>
<tbody>${rows || '<tr><td colspan="4">Операторы не расставлены</td></tr>'}</tbody></table>
${free.length ? `<p style="margin-top:10px">Без оператора: ${escHtml(free.join(', '))}</p>` : ''}
${d.note ? `<p>Примечание: ${escHtml(d.note)}</p>` : ''}
<p class="st">${d.doc?.status === 'confirmed'
    ? `Утверждено: ${escHtml(d.doc.confirmed_by || '')} ${ftime(d.doc.confirmed_at || '')}`
    : 'Черновик — не утверждено'}</p>
<div class="signs"><span>Мастер смены ______________________</span><span>Мастерица ______________________</span></div>`;
}

export function weekRange(day: string): {from: string; to: string} {
  const to = new Date(day.replace(/\./g, '-') + 'T12:00:00'), from = new Date(to);
  from.setDate(from.getDate() - 6);
  const fmt = (x: Date) => `${x.getFullYear()}.${String(x.getMonth() + 1).padStart(2, '0')}.${String(x.getDate()).padStart(2, '0')}`;
  return {from: fmt(from), to: fmt(to)};
}
