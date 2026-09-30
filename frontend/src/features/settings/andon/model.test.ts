import { describe, expect, it } from 'vitest';
import { clampMinutes } from './model';

describe('clampMinutes', () => {
  it('parses a valid integer', () => { expect(clampMinutes('15')).toBe('15'); });
  it('clamps negative numbers to zero', () => { expect(clampMinutes('-5')).toBe('0'); });
  it('treats garbage input as zero', () => { expect(clampMinutes('abc')).toBe('0'); });
  it('truncates a decimal to an integer', () => { expect(clampMinutes('12.9')).toBe('12'); });
});
