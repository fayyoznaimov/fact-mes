import { describe, expect, it } from 'vitest';
import { appliesLabel, categoryLabel, places } from './model';
import type { Reason, ReasonsResponse } from './model';

const response: ReasonsResponse = {
  reasons: [], categories: {scheduled: 'плановый простой'}, applies: {any: 'станок стоит или обесточен'},
};
const reason = (over: Partial<Reason>): Reason => ({
  id: 'water', name: 'Вода', en: 'Water', reason: 'Вода', applies: 'any', call: false,
  category: 'scheduled', color: null, sort: 10, in_operator: true, in_analytics: true,
  important: false, active: true, builtin: false, ...over,
});

describe('categoryLabel / appliesLabel', () => {
  it('resolves known ids to their labels', () => {
    expect(categoryLabel(response, 'scheduled')).toBe('плановый простой');
    expect(appliesLabel(response, 'any')).toBe('станок стоит или обесточен');
  });
  it('falls back to the raw id when unknown', () => {
    expect(categoryLabel(response, 'x')).toBe('x');
    expect(appliesLabel(response, 'x')).toBe('x');
  });
});

describe('places', () => {
  it('lists both places when both flags are set', () => { expect(places(reason({}))).toEqual(['в цеху', 'при разборе']); });
  it('lists only the operator place', () => { expect(places(reason({in_analytics: false}))).toEqual(['в цеху']); });
  it('is empty when neither flag is set', () => { expect(places(reason({in_operator: false, in_analytics: false}))).toEqual([]); });
});
