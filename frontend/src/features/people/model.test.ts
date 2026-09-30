import { describe, expect, it } from 'vitest';
import { importFactSummary, importSummary, roleLabel } from './model';

describe('roleLabel', () => {
  it('translates known roles', () => {
    expect(roleLabel('operator')).toBe('оператор');
    expect(roleLabel('master')).toBe('мастерица');
    expect(roleLabel('foreman')).toBe('мастер');
  });
  it('falls back to the raw value for unknown roles', () => { expect(roleLabel('admin')).toBe('admin'); });
});

describe('importSummary', () => {
  it('summarises a clean import', () => {
    expect(importSummary({in_list: 5, added: 2, updated: 1, same: 2, repeats: 0, skipped: []}))
      .toBe('В списке 5 человек: добавлено 2, обновлено 1, без изменений 2');
  });
  it('appends repeats and skipped lines when present', () => {
    expect(importSummary({in_list: 3, added: 1, updated: 0, same: 0, repeats: 2, skipped: ['bad line', 'another']}))
      .toBe('В списке 3 человек: добавлено 1, обновлено 0, без изменений 0; повторов 2; не разобрано строк 2: bad line | another');
  });
});

describe('importFactSummary', () => {
  it('summarises a FACT import', () => {
    expect(importFactSummary({found: 10, added: 3, total: 20})).toBe('Найдено имён в FACT: 10, добавлено новых: 3, всего в справочнике: 20');
  });
});
