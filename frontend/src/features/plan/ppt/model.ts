export type PptProduct = {
  product_code: string; orders: string[]; ppt_1c: number; ppt_fact: number | null;
  dev: number | null; sec_1c: number | null; norm_pct: number | null;
  days: number; clean_days: number; looms: string[]; verdict: string;
};
export type PptDay = {
  day: string; loom: string; order_no: string; product_code: string;
  ppt_1c: number; ppt_fact: number; dev: number | null; rows: number;
  norm_pct: number | null; time_eff: number; rpm: number | null; cloth: string;
  verdict: string; text: string;
};
export type PptCheckData = {products: PptProduct[]; days: PptDay[]; threshold: number};

export const sign = (v: number | null | undefined, nf: (x: unknown, d?: number) => string) =>
  v == null ? '' : (v > 0 ? '+' : '') + nf(v, 1) + '%';
export const isBad = (v: number | null | undefined, threshold: number) => v != null && Math.abs(v) > threshold;
export const verdictText = (d: PptDay) => d.verdict === 'ok' ? 'норма' : d.text.split(' — ').slice(1).join(' — ') || 'расхождение';
