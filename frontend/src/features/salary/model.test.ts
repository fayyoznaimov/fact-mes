import { describe, expect, it } from 'vitest';
import { mastersText, noteText, operatorOptions, rateUnitLabel, shiftLabel } from './model';
import type { Operator, SalaryResponse } from './model';

const fday = (v: unknown) => String(v).split('-').reverse().join('.');
const nf = (x: unknown) => String(x);

const baseTotals: SalaryResponse['totals'] = {
  picks: 0, kpicks: 0, salary: 0, salary_all: 0, unassigned_salary: 0, looms: 3, assigned: 3,
};

describe('shiftLabel', () => {
  it('formats the day and shift letter', () => {
    expect(shiftLabel(fday, {day: '2026-09-24', shift: 'A'})).toBe('24.09.2026 · смена A');
  });
});

describe('noteText', () => {
  it('reports how many looms have no operator', () => {
    const d = {totals: {...baseTotals, unassigned_salary: 500}, unassigned_looms: ['D1', 'D2']} as SalaryResponse;
    expect(noteText(d, nf)).toBe('Без оператора 2 станков из 3 — это 500 сум, которые пока никому не начислены.');
  });
  it('reports full coverage when nothing is unassigned', () => {
    const d = {totals: baseTotals, unassigned_looms: []} as unknown as SalaryResponse;
    expect(noteText(d, nf)).toBe('Все работавшие станки закреплены за операторами.');
  });
});

describe('rateUnitLabel', () => {
  it('labels the kpick unit', () => { expect(rateUnitLabel('kpick')).toBe('за 1000 пиков'); });
  it('labels the pick unit', () => { expect(rateUnitLabel('pick')).toBe('за пик'); });
});

describe('mastersText', () => {
  it('joins master names', () => { expect(mastersText([{id: 1, code: 'M1', name: 'Петрова'}, {id: 2, code: 'M2', name: 'Иванова'}])).toBe('Петрова, Иванова'); });
  it('shows a dash when there are none', () => { expect(mastersText([])).toBe('—'); });
});

describe('operatorOptions', () => {
  const operators: Operator[] = [
    {id: 1, code: 'O1', name: 'Иванова', role: 'operator', active: 1},
    {id: 2, code: 'O2', name: 'Сидорова', role: 'operator', active: 0},
    {id: 3, code: 'M1', name: 'Петрова', role: 'master', active: 1},
  ];
  it('offers a placeholder plus active non-master operators', () => {
    expect(operatorOptions(operators)).toEqual([
      {value: '', label: '— не назначен —'},
      {value: '1', label: 'Иванова (O1)'},
    ]);
  });
});
