import type { ClothMap, UnmappedCloth } from '../codes/model';

export type PlanLoom = {loom: string; from_day: string; to_day?: string; done: number; matched?: boolean; days?: number};
export type PlanCellsInfo = {first_day: string; last_day: string; cells: number; expected: number; shortfall: number};
export type PlanOrder = {
  id: number; order_no: string; product_code: string; qty_towels: number; source?: string;
  done: number; left: number; matched: boolean; percent: number; rate_per_day: number | null;
  days_left: number | null; eta: string | null; due_day: string | null; late_days: number | null;
  ppt_source?: string; closed?: boolean; looms: PlanLoom[]; plan: PlanCellsInfo | null;
};
export type PlanOnlyOrder = {order_no: string};
export type PlanData = {
  orders: PlanOrder[]; plan_only?: PlanOnlyOrder[]; products?: string[];
  cloth_map?: ClothMap[]; unmapped?: UnmappedCloth[];
};

export const PLAN_LIMIT = 60;

export type Tile = {label: string; value: string; bad?: boolean};
export function tiles(orders: PlanOrder[], nf: (x: unknown, d?: number) => string): Tile[] {
  const late = orders.filter(x => x.late_days != null && x.late_days > 0);
  const noRate = orders.filter(x => !x.rate_per_day && x.left > 0);
  return [
    {label: 'Заказов в работе', value: String(orders.length)},
    {label: 'Полотенец в плане', value: nf(orders.reduce((s, x) => s + x.qty_towels, 0))},
    {label: 'Сделано', value: nf(orders.reduce((s, x) => s + x.done, 0))},
    {label: 'Отстаём', value: String(late.length), bad: late.length > 0},
    {label: 'Без станка', value: String(noRate.length)},
  ];
}

export function pptSourcesNote(orders: PlanOrder[]): string {
  const srcs: Record<string, number> = {};
  orders.forEach(x => { const k = x.ppt_source || 'неизвестно'; srcs[k] = (srcs[k] || 0) + 1; });
  const list = Object.entries(srcs).map(([k, v]) => `${k} — ${v}`).join(', ');
  return (list ? `Пиков на изделие берём: ${list}. ` : '') + 'Значение из 1С или введённое вручную главнее расчёта по счётчикам.';
}

export function planOnlyNote(po: PlanOnlyOrder[]): string {
  if (!po.length) return '';
  return ` В плане цеха есть заказы, которых ещё нет из 1С: ${po.slice(0, 20).map(p => p.order_no).join(', ')}${po.length > 20 ? ' и ещё ' + (po.length - 20) : ''}.`;
}

export const progressColour = (lateDays: number | null) =>
  lateDays == null ? 'var(--muted)' : lateDays > 0 ? '#c4443b' : '#2f9e63';
