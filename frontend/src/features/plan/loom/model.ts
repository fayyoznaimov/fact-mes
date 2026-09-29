export type CellFact = {towels: number; eff: number; norm: number | null; cloth?: string};
export type Cell = {
  order_no?: string | null; product?: string | null; size?: string; design?: string; client?: string;
  gsm?: number | string; pile_yarn?: string | null; note?: string | null; product_code?: string | null;
  pick?: string | null; fact?: CellFact | null;
};
export type LoomRow = {loom: string; cells: Record<string, Cell>};
export type LoomGrid = {
  days: string[]; last_fact_day: string | null; plan_from: string | null; plan_to: string | null;
  plan_loaded_at: string | null; looms: LoomRow[];
};
export type CatalogProduct = {
  product_code: string; size?: string; design?: string; gsm?: number; qty: number; ppt?: number;
  weight_kg?: number; panels?: number; rolls?: number; due_day?: string; yarns?: Record<string, {yarn?: string; lot?: string}>;
  pile_yarn?: string; cells?: number; done: number; expected: number; looms?: string[];
};
export type CatalogOrder = {
  order_no: string; in_1c: boolean; in_plan: boolean; qty: number; due_day?: string; closed?: boolean;
  client?: string; product?: string; size?: string; design?: string; gsm?: number;
  products: CatalogProduct[]; cells: number; unpicked?: number; first_day?: string; last_day?: string;
  looms: string[]; done: number; expected: number; rate_now?: number; loaded_at?: string;
};
export type Catalog = {orders: CatalogOrder[]};

export type CellChange = {loom: string; day: string; order_no: string | null; product_code?: string | null;
  note?: string | null; product?: string | null; pile_yarn?: string | null; pick?: string | null};

export const SLOT_RU: Record<string, string> = {
  vors: 'ворс', karenoy: 'грунт', utog1: 'уток', utog2: 'кромка', utog2p: 'кромка кручёная',
  utog2x: 'кромка полиэстер', utog3: 'бордюр', utog3p: 'бордюр кручёная', utog4: 'бордюр полиэстер',
};

export const key = (loom: string, day: string) => loom + '|' + day;
export const split = (k: string): [string, string] => k.split('|') as [string, string];
export const cellSnapshot = (c: Cell | undefined): {order_no: string | null; note: string | null; product: string | null;
  pile_yarn: string | null; product_code: string | null; pick: string | null} => ({
  order_no: c?.order_no || null, note: c?.note || null, product: c?.product || null,
  pile_yarn: c?.pile_yarn || null, product_code: c?.product_code || null, pick: c?.pick || null,
});
export const isFilled = (c: Cell | undefined) => !!(c && (c.order_no || c.note || c.product));
export const hueOf = (s: string) => { let h = 0; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
export const weekday = (day: string) => new Date(day.replace(/\./g, '-') + 'T00:00').getDay();

export function orderByNo(catalog: CatalogOrder[], no: string | null | undefined): CatalogOrder | undefined {
  return catalog.find(x => x.order_no === String(no));
}

export type CellView = {
  key: string; classes: string[]; draggable: boolean; hue: number | null; title: string;
  headOrder: {order_no: string; ambiguous: boolean} | null; body: string; note: string | null;
  yarn: string | null; fact: {text: string; low: boolean; title: string} | null;
};

export function cellView(loom: string, day: string, grid: LoomGrid, catalog: CatalogOrder[], today: string,
  selected: boolean, focusOrder: string | null,
  nf: (x: unknown, d?: number) => string): CellView {
  const c = grid.looms.find(l => l.loom === loom)?.cells[day];
  const k = key(loom, day);
  const classes = ['d'];
  if (day === today) classes.push('today');
  if (day < today) classes.push('past');
  if (weekday(day) === 0) classes.push('wk');
  if (selected) classes.push('sel');
  if (c && c.order_no && c.order_no === focusOrder) classes.push('hl');
  if (!c) return {key: k, classes, draggable: false, hue: null, title: '', headOrder: null, body: '', note: null, fact: null, yarn: null};

  const ord = c.order_no ? orderByNo(catalog, c.order_no) : undefined;
  const ambiguous = !!(ord && ord.products.length > 1 && !c.product_code);
  if (ambiguous) classes.push('amb');
  const f = c.fact;
  const low = !!f && (f.norm != null ? f.norm < 90 : f.eff < 60);
  const showFact = !!f && day <= (grid.last_fact_day || '');
  const fact = showFact && f ? {
    low,
    title: `по FACT: ${f.cloth || ''} · КПД по времени ${nf(f.eff)}%${f.norm != null ? ` · выполнение нормы 1С ${nf(f.norm)}%` : ''}`,
    text: `${nf(f.towels)} шт · ${f.norm != null ? 'норма ' + nf(f.norm) + '%' : nf(f.eff) + '%'}`,
  } : null;
  const body = c.design ? `${c.size || ''} ${c.design}${c.client ? '/' + c.client : ''}${c.gsm ? ' · ' + c.gsm + ' GSM' : ''}`
    : c.product && c.product !== c.note ? c.product : '';
  const tip = [c.product, c.pile_yarn && 'ворс ' + c.pile_yarn, c.note,
    c.product_code ? '1С: ' + c.product_code + (c.pick === 'manual' ? ' (выбрано вручную)' : '')
      : !ambiguous ? '' : c.pick === 'nomatch'
        ? 'в заказе 1С нет изделия с таким размером, GSM и дизайном — проверьте план или выберите изделие (двойной щелчок)'
        : 'подходят несколько изделий заказа — выберите нужное (двойной щелчок)'].filter(Boolean).join(' · ');
  return {
    key: k, classes, draggable: isFilled(c), hue: c.order_no ? hueOf(c.order_no) : null, title: tip,
    headOrder: c.order_no ? {order_no: c.order_no, ambiguous} : null,
    body, note: c.note || null, yarn: c.pile_yarn || null, fact,
  };
}

export function daysFrom(startDay: string, n: number, skipSundays: boolean): string[] {
  const out: string[] = [];
  const t = new Date(startDay.replace(/\./g, '-') + 'T00:00');
  while (out.length < n) {
    if (!(skipSundays && t.getDay() === 0)) out.push(ymd(t));
    t.setDate(t.getDate() + 1);
  }
  return out;
}
export const ymd = (t: Date) => t.getFullYear() + '.' + String(t.getMonth() + 1).padStart(2, '0') + '.' + String(t.getDate()).padStart(2, '0');
export const dash2dot = (v: string) => (v || '').replace(/-/g, '.');

export type OrderFilter = 'all' | '1c' | 'no1c' | 'short' | 'free';
export function filterOrders(catalog: CatalogOrder[], query: string, filter: OrderFilter): CatalogOrder[] {
  const q = query.trim().toLowerCase();
  return catalog.filter(o => {
    if (o.closed && !o.in_plan) return false;
    if (filter === '1c' && !o.in_1c) return false;
    if (filter === 'no1c' && o.in_1c) return false;
    if (filter === 'short' && !(o.qty && o.expected < o.qty)) return false;
    if (filter === 'free' && o.cells) return false;
    return !q || [o.order_no, o.product, o.design, o.client && '/' + o.client,
      ...o.products.map(p => p.product_code)].filter(Boolean).join(' ').toLowerCase().includes(q);
  });
}

export function orderProgress(o: CatalogOrder): {done: number; expected: number} {
  return {
    done: o.qty ? Math.min(100, 100 * o.done / o.qty) : 0,
    expected: o.qty ? Math.min(100, 100 * o.expected / o.qty) : 0,
  };
}

export const idxOf = (k: string, looms: string[], days: string[]): [number, number] => {
  const [l, d] = split(k); return [looms.indexOf(l), days.indexOf(d)];
};
export function topLeft(keys: string[], looms: string[], days: string[]): string {
  return keys.reduce((best, k) => {
    const [a, b] = idxOf(k, looms, days), [x, y] = idxOf(best, looms, days);
    return a < x || (a === x && b < y) ? k : best;
  }, keys[0]);
}

export type DialogInitial = {
  loom: string; day: string; heading: string; order: string; note: string;
  selectedProduct: string | null; hint: string;
};
export function dialogInitial(keys: string[], forcedOrder: string | undefined, grid: LoomGrid,
  catalog: CatalogOrder[], dmy: (d: string) => string): DialogInitial {
  const [loom, day] = split(keys[0]);
  const c = grid.looms.find(x => x.loom === loom)?.cells[day];
  const one = keys.length === 1 && !forcedOrder;
  const heading = (keys.length > 1 ? `Клеток: ${keys.length}` : `${loom} · ${dmy(day)}.${day.slice(0, 4)}`)
    + (forcedOrder ? ` · заказ ${forcedOrder}` : '');
  return {
    loom, day, heading, order: forcedOrder || (one ? c?.order_no || '' : ''), note: one ? c?.note || '' : '',
    selectedProduct: one ? c?.product_code || null : null,
    hint: forcedOrder ? 'В заказе несколько изделий — выберите, какое ставить на станок.'
      : c?.product ? 'Сейчас: ' + c.product + (c.pile_yarn ? ' · ворс ' + c.pile_yarn : '') : '',
  };
}
export function productOptions(orderNo: string, catalog: CatalogOrder[]): CatalogProduct[] {
  const o = orderByNo(catalog, orderNo.trim());
  return o ? o.products : [];
}
