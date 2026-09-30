import { describe, expect, it } from 'vitest';
import { dash2dot, docStatusLabel, unitLabel } from './model';

describe('unitLabel', () => {
  it('labels kpick', () => { expect(unitLabel('kpick')).toBe('за 1000 пиков'); });
  it('labels pick', () => { expect(unitLabel('pick')).toBe('за пик'); });
});

describe('docStatusLabel', () => {
  it('labels a posted document', () => { expect(docStatusLabel('posted')).toBe('проведён'); });
  it('labels anything else as cancelled', () => { expect(docStatusLabel('cancelled')).toBe('отменён'); });
});

describe('dash2dot', () => {
  it('converts dashes to dots', () => { expect(dash2dot('2026-09-25')).toBe('2026.09.25'); });
});
