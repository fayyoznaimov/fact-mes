import { describe, expect, it } from 'vitest';
import { shiftLabel, styleText } from './model';

describe('shiftLabel', () => {
  it('formats the day and shift letter', () => {
    const fday = (v: unknown) => String(v).split('-').reverse().join('.');
    expect(shiftLabel(fday, {day: '2026-09-24', shift: 'B'})).toBe('24.09.2026 · смена B');
  });
});

describe('styleText', () => {
  it('passes through a real style', () => { expect(styleText('D327')).toBe('D327'); });
  it('treats "Undefined" as not set', () => { expect(styleText('Undefined')).toBeNull(); });
  it('treats an empty string as not set', () => { expect(styleText('')).toBeNull(); });
});
