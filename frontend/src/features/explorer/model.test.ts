import { describe, expect, it } from 'vitest';
import { causeColor, causeShare, defaultRange, orderRange, shiftsParam, sortedCauses, toggleShift } from './model';

describe('causeColor', () => {
  it('maps known Russian cause names to the shared palette', () => {
    expect(causeColor('Уток')).toBe('#df5656');
    expect(causeColor('Прочее')).toBe('#bd737c');
  });
  it('uses its own colors for doffing/warp-out, not the stop-cause palette', () => {
    expect(causeColor('Сход навоя')).toBe('#3f9c96');
    expect(causeColor('Съём ткани')).toBe('#8e9a3a');
  });
  it('falls back to "Other" for an unrecognised name', () => { expect(causeColor('???')).toBe('#bd737c'); });
});

describe('sortedCauses / causeShare', () => {
  it('sorts causes by hours descending', () => {
    expect(sortedCauses({'Уток': 2, 'Основа': 5, 'Прочее': 1})).toEqual([['Основа', 5], ['Уток', 2], ['Прочее', 1]]);
  });
  it('computes each cause share of the total', () => {
    expect(causeShare([['A', 3], ['B', 1]])).toEqual([{name: 'A', hours: 3, pct: 75}, {name: 'B', hours: 1, pct: 25}]);
  });
  it('avoids division by zero for an empty set', () => { expect(causeShare([])).toEqual([]); });
});

describe('orderRange', () => {
  it('keeps ascending order as-is', () => { expect(orderRange('2026.09.01', '2026.09.10')).toEqual(['2026.09.01', '2026.09.10']); });
  it('swaps a reversed range', () => { expect(orderRange('2026.09.10', '2026.09.01')).toEqual(['2026.09.01', '2026.09.10']); });
});

describe('defaultRange', () => {
  it('picks the most recent day as "to" and 30 days back (or the earliest) as "from"', () => {
    const days = Array.from({length: 40}, (_, i) => `day${i}`); // day0 = most recent
    expect(defaultRange(days)).toEqual({from: 'day29', to: 'day0'});
  });
  it('uses the earliest day when there are fewer than 30', () => {
    expect(defaultRange(['d2', 'd1', 'd0'])).toEqual({from: 'd0', to: 'd2'});
  });
  it('handles an empty list', () => { expect(defaultRange([])).toEqual({from: '', to: ''}); });
});

describe('toggleShift', () => {
  it('toggles a shift letter on and off', () => {
    const s = toggleShift(new Set(['A', 'B']), 'B');
    expect(s).toEqual(new Set(['A']));
  });
  it('refuses to remove the last remaining shift', () => {
    const s = toggleShift(new Set(['A']), 'A');
    expect(s).toEqual(new Set(['A']));
  });
});

describe('shiftsParam', () => {
  it('joins selected shifts in A/B/C order regardless of set insertion order', () => {
    expect(shiftsParam(new Set(['C', 'A']))).toBe('AC');
  });
});
