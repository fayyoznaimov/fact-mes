import { describe, expect, it } from 'vitest';
import { hms, isHotCell, noneColClass, paintEff, rowKeyLabel, unexplainedMinutes } from './model';
import type { Cat, Column, ManualRow } from './model';

describe('hms', () => {
  it('shows minutes:seconds under an hour', () => { expect(hms(125)).toBe('2:05'); });
  it('shows hours:minutes:seconds past an hour', () => { expect(hms(3725)).toBe('1:02:05'); });
  it('shows a dash for null', () => { expect(hms(null)).toBe('—'); });
});

describe('paintEff', () => {
  it('flags red below 70', () => { expect(paintEff(50)).toBe(' c-red'); });
  it('flags yellow 70-79', () => { expect(paintEff(75)).toBe(' c-yel'); });
  it('leaves 80+ unpainted', () => { expect(paintEff(85)).toBe(''); });
  it('leaves 0 and below unpainted', () => { expect(paintEff(0)).toBe(''); });
  it('handles null', () => { expect(paintEff(null)).toBe(''); });
});

describe('noneColClass / isHotCell', () => {
  const none: Column = {id: 'unexplained', name: 'Без причины', kind: 'none'};
  const machine: Column = {id: 'warp_out', name: 'Сход навоя', kind: 'machine'};
  it('marks "none" columns', () => {
    expect(noneColClass(none)).toBe(' none-col');
    expect(noneColClass(machine)).toBe('');
  });
  it('flags a "none" cell over 5% as hot', () => {
    const cat: Cat = {n: 1, min: 10, avg_sec: 600, pct: 6};
    expect(isHotCell(none, cat)).toBe(true);
    expect(isHotCell(machine, cat)).toBe(false);
    expect(isHotCell(none, {...cat, pct: 4})).toBe(false);
    expect(isHotCell(none, undefined)).toBe(false);
  });
});

describe('rowKeyLabel', () => {
  const fday = (v: unknown) => String(v).split('.').reverse().join('-');
  it('formats the key as a date for the "day" grouping', () => {
    expect(rowKeyLabel({key: '2026.09.24'} as ManualRow, 'day', fday)).toBe('24-09-2026');
  });
  it('leaves the key as-is for other groupings', () => {
    expect(rowKeyLabel({key: 'D1'} as ManualRow, 'loom', fday)).toBe('D1');
  });
});

describe('unexplainedMinutes', () => {
  it('reads the unexplained category minutes', () => {
    expect(unexplainedMinutes({cats: {unexplained: {n: 1, min: 42, avg_sec: null, pct: 1}}} as unknown as ManualRow)).toBe(42);
  });
  it('defaults to 0 when missing', () => { expect(unexplainedMinutes({cats: {}} as unknown as ManualRow)).toBe(0); });
});
