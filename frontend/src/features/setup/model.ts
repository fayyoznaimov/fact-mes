import type { YarnRow } from './bridge';

export type Column = {
  k: string; t: string;
  num?: true; sep?: true; design?: true; yarn?: true; lot?: true; slot?: string;
};

export const SG_YARN_RU: Record<string, string> = {
  pile: 'Ворс', ground: 'Грунт', weft1: 'Уток', weft2: 'Кромка',
  hemply: 'Кромка кручён.', hempoly: 'Кромка полиэст.', weft3: 'Бордюр',
  fancyply: 'Бордюр кручён.', weft4: 'Бордюр полиэст.',
};
export const SG_RARE = ['hemply', 'hempoly', 'fancyply', 'weft4'];
export const SG_NUMS: Column[] = [
  {k: 'gsm', t: 'GSM', num: true}, {k: 'weight_kg', t: 'Вес шт, кг', num: true},
  {k: 'ppt', t: 'PPT', num: true}, {k: 'panels', t: 'Панели', num: true},
];
export const SG_DESIGN: Column = {k: 'design', t: 'Дизайн', design: true};
export const YARN_KINDS: Record<string, string> = {'': '—', pile: 'ворс', ground: 'грунт', weft: 'уток'};

export type SetupGridRow = {
  loom: string; cloth: string | null; design: string | null;
  values: Record<string, string | number | null>;
  manual: Record<string, boolean>;
  from_day?: string | null; set_by?: string | null;
};
export type SetupGridResponse = {day: string; report_day: string | null; rows: SetupGridRow[]};

export function sgColsFor(rows: SetupGridRow[]): Column[] {
  return [SG_DESIGN, ...SG_NUMS, ...Object.entries(SG_YARN_RU)
    .filter(([y]) => !SG_RARE.includes(y) || rows.some(r => r.values[y + '_yarn'] || r.values[y + '_lot']))
    .flatMap(([y, t]): Column[] => [
      {k: `${y}_yarn`, t, yarn: true, sep: true, slot: y},
      {k: `${y}_lot`, t: 'лот', lot: true, slot: y},
    ])];
}

export const fmtv = (v: unknown): string =>
  v == null ? '' : (typeof v === 'number' ? String(+v.toFixed(4)) : String(v));

// То же, что на сервере: «20/2spun» → «20/2 SPUN», сравнение — без пробелов.
export const yarnCanon = (s: unknown): string => String(s || '').toUpperCase().replace(/\s+/g, ' ').trim()
  .replace(/\s*\/\s*/g, '/').replace(/^(\d+(?:\/\d+)?)\s*([A-ZА-ЯЁ])/, '$1 $2');
export const yarnKey = (s: unknown): string => yarnCanon(s).replace(/ /g, '');

export function yarnBad(value: string, yarns: YarnRow[]): boolean {
  const v = value.trim();
  if (!v) return false;
  return !yarns.some(y => y.active && y.key === yarnKey(v));
}

// Одно написание на одну пряжу: если введённый текст совпадает по ключу с активной
// пряжей справочника, но записан иначе — заменить на справочное написание.
export function yarnCanonicalize(value: string, yarns: YarnRow[]): string {
  const y = yarns.find(x => x.active && x.key === yarnKey(value));
  return y && value !== y.name ? y.name : value;
}

export function sgInFilter(loom: string, filter: string): boolean {
  const f = filter.trim();
  return !f || textTest(f)(loom);
}

// Тот же фильтр станков, что и везде в приложении: «D, J1-J14» — список имён и диапазонов.
export function textTest(expr: string): (value: string) => boolean {
  const items = expr.toUpperCase().split(/[,\s]+/).filter(Boolean);
  const pp = (s: string) => s.match(/^([A-Z]+)(\d+)$/) || [];
  return (v: unknown) => {
    const name = String(v || '').toUpperCase();
    return items.some(it => {
      const [from, to] = it.split('-');
      if (to) {
        const a = pp(from), b = pp(to), c = pp(name);
        return !!a[1] && c[1] === a[1] && +c[2] >= +a[2] && +c[2] <= +b[2];
      }
      return /^[A-Z]+$/.test(it) ? name.startsWith(it) && /^\d+$/.test(name.slice(it.length))
        : name === it;
    });
  };
}

export const dash2dot = (v: string): string => (v || '').replace(/-/g, '.');

// Текущая смена по местному времени браузера — как на цеховых часах в шапке.
export function shiftNow(): {day: string; sh: string} {
  const d = new Date(), h = d.getHours();
  const sh = h >= 7 && h < 15 ? 'A' : h >= 15 && h < 23 ? 'B' : 'C';
  if (h < 7) d.setDate(d.getDate() - 1);
  return {day: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`, sh};
}

export function rowsDirty(cells: Record<string, string>[], original: Record<string, string>[], cols: Column[]): number[] {
  return cells.map((row, r) => cols.some(c => row[c.k] !== original[r][c.k]) ? r : -1).filter(r => r >= 0);
}

export function anyBad(cells: Record<string, string>[], cols: Column[], yarns: YarnRow[]): boolean {
  return cells.some(row => cols.some(c => c.yarn && yarnBad(row[c.k] || '', yarns)));
}

export function applyPaste(cells: Record<string, string>[], cols: Column[], r0: number, c0: number,
  text: string, visibleRows: number[]): {cells: Record<string, string>[]; count: number; overflow: boolean} {
  const body = text.replace(/\r/g, '').replace(/\n+$/, '');
  const lines = body.split('\n');
  const rows = visibleRows.filter(r => r >= r0);
  const next = cells.map(row => ({...row}));
  let count = 0;
  lines.forEach((line, dr) => {
    const r = rows[dr];
    if (r == null) return;
    line.split('\t').forEach((v, dc) => {
      const col = cols[c0 + dc];
      if (col) { next[r][col.k] = v.trim(); count++; }
    });
  });
  return {cells: next, count, overflow: lines.length > rows.length};
}

export function badYarnNames(cells: Record<string, string>[], cols: Column[], yarns: YarnRow[]): string[] {
  const names = new Set<string>();
  cells.forEach(row => cols.forEach(c => {
    if (c.yarn && yarnBad(row[c.k] || '', yarns)) names.add(yarnCanon(row[c.k]));
  }));
  return [...names];
}
