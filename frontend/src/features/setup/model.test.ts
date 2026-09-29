import { describe, expect, it } from 'vitest';
import type { YarnRow } from './bridge';
import type { SetupGridRow } from './model';
import {
  anyBad, applyPaste, badYarnNames, fmtv, rowsDirty, sgColsFor, sgInFilter,
  textTest, yarnBad, yarnCanon, yarnCanonicalize, yarnKey,
} from './model';

describe('sgColsFor', () => {
  const row = (values: Record<string, string>): SetupGridRow => ({loom: 'D1', cloth: null, design: null, values, manual: {}});
  it('includes the always-shown yarn slots even with no data', () => {
    const cols = sgColsFor([row({})]);
    expect(cols.map(c => c.k)).toContain('pile_yarn');
    expect(cols.map(c => c.k)).toContain('weft2_lot');
  });
  it('hides rare slots (hemply/hempoly/fancyply/weft4) unless some row uses them', () => {
    const cols = sgColsFor([row({})]);
    expect(cols.map(c => c.k)).not.toContain('hemply_yarn');
  });
  it('shows a rare slot once any row has a value in it', () => {
    const cols = sgColsFor([row({hemply_yarn: '16/1 SPUN'})]);
    expect(cols.map(c => c.k)).toContain('hemply_yarn');
    expect(cols.map(c => c.k)).toContain('hemply_lot');
  });
  it('always starts with the design column', () => {
    expect(sgColsFor([row({})])[0].k).toBe('design');
  });
});

describe('fmtv', () => {
  it('formats null/undefined as empty string', () => { expect(fmtv(null)).toBe(''); expect(fmtv(undefined)).toBe(''); });
  it('trims trailing float noise from numbers', () => { expect(fmtv(635.00001)).toBe('635'); });
  it('passes strings through', () => { expect(fmtv('D144')).toBe('D144'); });
});

describe('yarnCanon / yarnKey', () => {
  it('normalizes spacing, case and slash spacing', () => {
    expect(yarnCanon('16/1spun')).toBe('16/1 SPUN');
    expect(yarnCanon('12 / 1')).toBe('12/1');
  });
  it('key strips spaces so different spacings match', () => {
    expect(yarnKey('16/1 SPUN')).toBe(yarnKey('16/1spun'));
  });
});

const yarns: YarnRow[] = [
  {id: 1, name: '16/1 SPUN', key: '16/1SPUN', kind: 'pile', active: true},
  {id: 2, name: 'OLD YARN', key: 'OLDYARN', kind: '', active: false},
];

describe('yarnBad / yarnCanonicalize', () => {
  it('is not bad when empty', () => { expect(yarnBad('', yarns)).toBe(false); });
  it('is bad when no active yarn matches the key', () => {
    expect(yarnBad('unknown yarn', yarns)).toBe(true);
    expect(yarnBad('OLD YARN', yarns)).toBe(true); // inactive doesn't count
  });
  it('is not bad when an active yarn matches by key regardless of spacing', () => {
    expect(yarnBad('16/1spun', yarns)).toBe(false);
  });
  it('canonicalizes to the active yarn\'s exact spelling', () => {
    expect(yarnCanonicalize('16/1spun', yarns)).toBe('16/1 SPUN');
  });
  it('leaves unmatched or already-correct text untouched', () => {
    expect(yarnCanonicalize('16/1 SPUN', yarns)).toBe('16/1 SPUN');
    expect(yarnCanonicalize('nothing like it', yarns)).toBe('nothing like it');
  });
});

describe('sgInFilter / textTest', () => {
  it('matches everything when the filter is empty', () => { expect(sgInFilter('D1', '')).toBe(true); });
  it('matches a plain prefix+number pattern', () => { expect(sgInFilter('D1', 'D')).toBe(true); });
  it('matches a numeric range', () => { expect(textTest('J1-J14')('J7')).toBe(true); expect(textTest('J1-J14')('J15')).toBe(false); });
  it('matches an exact non-prefix name', () => { expect(textTest('D1')('D1')).toBe(true); expect(textTest('D1')('D10')).toBe(false); });
});

describe('rowsDirty', () => {
  const cols = sgColsFor([]);
  it('finds no dirty rows when cells equal originals', () => {
    const cells = [{design: 'D1'}], original = [{design: 'D1'}];
    expect(rowsDirty(cells, original, [{k: 'design', t: 'Дизайн', design: true}])).toEqual([]);
  });
  it('flags a row where any tracked column differs', () => {
    const cells = [{design: 'D2'}, {design: 'D1'}], original = [{design: 'D1'}, {design: 'D1'}];
    expect(rowsDirty(cells, original, [{k: 'design', t: 'Дизайн', design: true}])).toEqual([0]);
  });
  void cols;
});

describe('anyBad / badYarnNames', () => {
  const cols = [{k: 'pile_yarn', t: 'Ворс', yarn: true as const, slot: 'pile'}];
  it('reports no bad cells when all yarn values are known', () => {
    expect(anyBad([{pile_yarn: '16/1 SPUN'}], cols, yarns)).toBe(false);
  });
  it('reports bad cells and collects their canonical names, deduplicated', () => {
    expect(anyBad([{pile_yarn: 'unknown'}, {pile_yarn: 'UNKNOWN'}], cols, yarns)).toBe(true);
    expect(badYarnNames([{pile_yarn: 'unknown'}, {pile_yarn: 'UNKNOWN'}], cols, yarns)).toEqual(['UNKNOWN']);
  });
});

describe('applyPaste', () => {
  const cols = [{k: 'a', t: 'A'}, {k: 'b', t: 'B'}];
  const cells = [{a: '1', b: '2'}, {a: '3', b: '4'}, {a: '5', b: '6'}];
  it('distributes a tab/newline block starting at the given cell over visible rows below', () => {
    const r = applyPaste(cells, cols, 0, 0, 'x\ty\nz\tw', [0, 1, 2]);
    expect(r.cells).toEqual([{a: 'x', b: 'y'}, {a: 'z', b: 'w'}, {a: '5', b: '6'}]);
    expect(r.count).toBe(4);
    expect(r.overflow).toBe(false);
  });
  it('skips rows hidden by the filter', () => {
    const r = applyPaste(cells, cols, 0, 0, 'x\ny', [0, 2]);
    expect(r.cells[1]).toEqual({a: '3', b: '4'}); // row 1 is hidden, untouched
    expect(r.cells[2].a).toBe('y');
  });
  it('flags overflow when there are more lines than rows below', () => {
    const r = applyPaste(cells, cols, 2, 0, 'x\ny\nz', [0, 1, 2]);
    expect(r.overflow).toBe(true);
  });
});
