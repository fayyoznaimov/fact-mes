export type Unit = 'kpick' | 'pick';
export type RatePeriod = {
  id: number; valid_from: string; rate: number; unit: Unit;
  doc_id: number | null; set_by: string; set_at: string; number: string | null; status: string | null;
};
export type RatesResponse = {day: string; rate: number; unit: Unit; periods: RatePeriod[]};

export function unitLabel(unit: Unit): string {
  return unit === 'kpick' ? 'за 1000 пиков' : 'за пик';
}

export function docStatusLabel(status: string): string {
  return status === 'posted' ? 'проведён' : 'отменён';
}

export const dash2dot = (v: string): string => (v || '').replace(/-/g, '.');
