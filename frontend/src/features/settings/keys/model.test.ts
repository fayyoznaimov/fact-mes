import { describe, expect, it } from 'vitest';
import { scopesText } from './model';
import type { ApiKey } from './model';

const key = (scopes: string): ApiKey => ({
  id: 1, name: '1С', prefix: 'mes_abc', scopes, active: true, created_by: 'admin', created_at: null, last_used_at: null,
});
const labels = {read: 'читать данные', write: 'присылать заказы и техкарты', tickets: 'заводить и разбирать тикеты'};

describe('scopesText', () => {
  it('joins known scope labels', () => {
    expect(scopesText(key('read write'), labels)).toBe('читать данные, присылать заказы и техкарты');
  });
  it('falls back to the raw scope name when unknown', () => {
    expect(scopesText(key('read custom'), labels)).toBe('читать данные, custom');
  });
});
