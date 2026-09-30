export type Shift = {day: string; shift: string};

export type Operator = {id: number; code: string; name: string; role: string; active: number | boolean};

export type SalaryTotals = {
  picks: number; kpicks: number; salary: number; salary_all: number;
  unassigned_salary: number; looms: number; assigned: number;
};
export type SalaryOperatorRow = {
  operator_id: number; code: string; name: string; looms: string[]; loom_count: number;
  picks: number; kpicks: number; salary: number; effic: number;
  weft_ct: number; top_ct: number; warp_ct: number;
  weft_cmpx: number; warp_cmpx: number; wait_min: number; manual_ct: number;
};
export type SalaryLoomRow = {
  loom: string; style: string; picks: number; kpicks: number; salary: number; effic: number | null;
  weft_ct: number; warp_ct: number; wait_min: number;
  operator_id: number | null; operator: string | null;
};
export type SalaryMaster = {id: number; code: string; name: string};
export type SalaryResponse = {
  day: string; shift: string; rate: number; rate_unit: string;
  operators: SalaryOperatorRow[]; masters: SalaryMaster[];
  unassigned_looms: string[]; looms: SalaryLoomRow[]; totals: SalaryTotals;
};

export function shiftLabel(fday: (v: unknown) => string, s: Shift): string {
  return `${fday(s.day)} · смена ${s.shift}`;
}

export function noteText(d: SalaryResponse, nf: (x: unknown, digits?: number) => string): string {
  return d.unassigned_looms.length
    ? `Без оператора ${d.unassigned_looms.length} станков из ${d.totals.looms} — это ${nf(d.totals.unassigned_salary)} сум, которые пока никому не начислены.`
    : 'Все работавшие станки закреплены за операторами.';
}

export function rateUnitLabel(unit: string): string {
  return unit === 'kpick' ? 'за 1000 пиков' : 'за пик';
}

export function mastersText(masters: SalaryMaster[]): string {
  return masters.map(m => m.name).join(', ') || '—';
}

export function operatorOptions(operators: Operator[]): {value: string; label: string}[] {
  return [
    {value: '', label: '— не назначен —'},
    ...operators.filter(o => o.role !== 'master' && o.active !== 0)
      .map(o => ({value: String(o.id), label: `${o.name} (${o.code})`})),
  ];
}
