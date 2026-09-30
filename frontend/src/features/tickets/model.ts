export type Category = {
  id: string; name: string; en: string; reason: string; applies: string; call: boolean;
  category: string; color: string; sort: number; in_operator: boolean; in_analytics: boolean;
  important: boolean; active: boolean; builtin: boolean;
};
export type Ticket = {
  id: number; loom: string; started_at: string; ended_at: string | null; duration_sec: number;
  fact_cause: string | null; style: string | null; shift: string | null; category_id: string | null;
  comment: string | null; opened_by: string | null; classified_by: string | null; classified_at: string | null;
  escalated_at: string | null;
  reason: string; reason_from: string; cause_ru: string | null; category_name: string | null; open: boolean;
};
export type TicketsResponse = {tickets: Ticket[]; categories: Category[]; can_edit: boolean};
export type LiveLoom = {loom: string; needs_ticket: boolean; cause_ru: string; state_sec: number};
export type LiveResponse = {looms: LiveLoom[]; totals: {stopped: number}};

export type Filter = 'all' | 'open' | 'noreason';
export type SortKey = 'loom' | 'started_at' | 'shift' | 'duration_sec' | 'cause_ru' | 'reason' | 'category_name';
export type Sort = {k: SortKey; dir: 1 | -1};

export const dash2dot = (v: string): string => (v || '').replace(/-/g, '.');

export function todayForShift(now: Date): string {
  const d = new Date(now);
  if (d.getHours() < 7) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function dur(sec: number): string {
  sec = Math.max(0, sec | 0);
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60);
  return h ? `${h} ч ${String(m).padStart(2, '0')} мин` : `${m} мин`;
}

export function textTest(expr: string): (v: string) => boolean {
  const items = expr.toUpperCase().split(/[,\s]+/).filter(Boolean);
  const pp = (s: string) => s.match(/^([A-Z]+)(\d+)$/) || [];
  return (v: string) => {
    const name = String(v || '').toUpperCase();
    return items.some(it => {
      const [from, to] = it.split('-');
      if (to) {
        const a = pp(from), b = pp(to), c = pp(name);
        return !!a[1] && c[1] === a[1] && +c[2] >= +a[2] && +c[2] <= +b[2];
      }
      return /^[A-Z]+$/.test(it) ? name.startsWith(it) && /^\d+$/.test(name.slice(it.length)) : name === it;
    });
  };
}

function sortValue(r: Ticket, k: SortKey): string | number {
  switch (k) {
    case 'loom': return (r.loom || '').replace(/\d+/, d => d.padStart(3, '0'));
    case 'started_at': return r.started_at || '';
    case 'shift': return r.shift || '';
    case 'duration_sec': return r.duration_sec || 0;
    case 'cause_ru': return r.cause_ru || '';
    case 'reason': return r.reason || '';
    case 'category_name': return r.category_name || '';
  }
}

export function nextSort(current: Sort, k: SortKey): Sort {
  return {
    k,
    dir: current.k === k ? (current.dir === 1 ? -1 : 1) : (k === 'started_at' || k === 'duration_sec' ? -1 : 1),
  };
}

export function filterRows(rows: Ticket[], shift: string, loomsExpr: string, filter: Filter): Ticket[] {
  const test = loomsExpr.trim() ? textTest(loomsExpr) : null;
  return rows.filter(r => (!shift || (r.shift || '').endsWith('.' + shift))
    && (!test || test(r.loom)) && (filter !== 'noreason' || !r.category_id));
}

export function sortRows(rows: Ticket[], sort: Sort): Ticket[] {
  return [...rows].sort((a, b) => {
    const ka = sortValue(a, sort.k), kb = sortValue(b, sort.k);
    return (ka > kb ? 1 : ka < kb ? -1 : 0) * sort.dir;
  });
}

export function visibleRows(rows: Ticket[], shift: string, loomsExpr: string, filter: Filter, sort: Sort): Ticket[] {
  return sortRows(filterRows(rows, shift, loomsExpr, filter), sort);
}

export type Tile = {label: string; value: string | number; sub?: string};
export function buildTiles(rows: Ticket[], stopped: number | null): Tile[] {
  const sum = (a: Ticket[]) => a.reduce((x, r) => x + (r.duration_sec || 0), 0);
  const noreason = rows.filter(r => !r.category_id);
  const by: Record<string, {n: number; s: number}> = {};
  rows.forEach(r => { const b = by[r.reason] = by[r.reason] || {n: 0, s: 0}; b.n++; b.s += r.duration_sec || 0; });
  const top = Object.entries(by).sort((a, b) => b[1].s - a[1].s).slice(0, 4);
  return [
    {label: 'Тикетов', value: rows.length},
    {label: 'Простой', value: dur(sum(rows))},
    {label: 'Без причины', value: noreason.length, sub: dur(sum(noreason))},
    {label: 'Стоит сейчас', value: stopped ?? '—'},
    ...top.map(([reason, b]) => ({label: reason, value: dur(b.s), sub: String(b.n)})),
  ];
}

export function shortTime(ftime: (v: unknown) => string, v: string): string {
  const t = ftime(v);
  return t.slice(0, 5) + t.slice(10);
}
