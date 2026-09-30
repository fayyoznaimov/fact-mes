import { describe, expect, it } from 'vitest';
import { buildTiles, dur, filterRows, nextSort, shortTime, sortRows, textTest, todayForShift, visibleRows } from './model';
import type { Sort, Ticket } from './model';

const t = (over: Partial<Ticket>): Ticket => ({
  id: 1, loom: 'D1', started_at: '2026-09-25T08:00:00', ended_at: null, duration_sec: 600,
  fact_cause: 'Manual', style: null, shift: '2026.09.25.A', category_id: null, comment: null,
  opened_by: null, classified_by: null, classified_at: null, escalated_at: null,
  reason: 'Ручной останов', reason_from: 'FACT', cause_ru: 'Ручной останов', category_name: null, open: true,
  ...over,
});

describe('todayForShift', () => {
  it('keeps the calendar day during A/B/C daytime hours', () => {
    expect(todayForShift(new Date('2026-09-25T10:00:00'))).toBe('2026-09-25');
  });
  it('rolls back to the previous day in the small hours of shift C', () => {
    expect(todayForShift(new Date('2026-09-25T03:00:00'))).toBe('2026-09-24');
  });
});

describe('dur', () => {
  it('formats minutes under an hour', () => { expect(dur(300)).toBe('5 мин'); });
  it('formats hours and minutes', () => { expect(dur(3900)).toBe('1 ч 05 мин'); });
  it('clamps negative values to zero', () => { expect(dur(-10)).toBe('0 мин'); });
});

describe('textTest', () => {
  it('matches an exact loom name', () => { expect(textTest('D1')('D1')).toBe(true); expect(textTest('D1')('D2')).toBe(false); });
  it('matches a bare prefix like "D" against any D-numbered loom', () => {
    const test = textTest('D');
    expect(test('D1')).toBe(true); expect(test('D14')).toBe(true); expect(test('J1')).toBe(false);
  });
  it('matches a numeric range like J1-J14', () => {
    const test = textTest('J1-J14');
    expect(test('J1')).toBe(true); expect(test('J10')).toBe(true); expect(test('J14')).toBe(true);
    expect(test('J15')).toBe(false); expect(test('D1')).toBe(false);
  });
  it('accepts multiple comma or space separated items', () => {
    const test = textTest('D, J1-J14');
    expect(test('D3')).toBe(true); expect(test('J5')).toBe(true); expect(test('J20')).toBe(false);
  });
});

describe('nextSort', () => {
  it('flips direction when clicking the same column', () => {
    expect(nextSort({k: 'loom', dir: 1}, 'loom')).toEqual({k: 'loom', dir: -1});
  });
  it('defaults new time/duration columns to descending', () => {
    expect(nextSort({k: 'loom', dir: 1}, 'started_at')).toEqual({k: 'started_at', dir: -1});
    expect(nextSort({k: 'loom', dir: 1}, 'duration_sec')).toEqual({k: 'duration_sec', dir: -1});
  });
  it('defaults other columns to ascending', () => {
    expect(nextSort({k: 'started_at', dir: -1}, 'loom')).toEqual({k: 'loom', dir: 1});
  });
});

describe('filterRows', () => {
  const rows = [t({id: 1, loom: 'D1', shift: '2026.09.25.A', category_id: null}),
    t({id: 2, loom: 'D2', shift: '2026.09.25.B', category_id: 'electric'})];
  it('filters by shift suffix', () => { expect(filterRows(rows, 'A', '', 'all').map(r => r.id)).toEqual([1]); });
  it('filters by loom pattern', () => { expect(filterRows(rows, '', 'D2', 'all').map(r => r.id)).toEqual([2]); });
  it('filters to rows without a category when "noreason"', () => {
    expect(filterRows(rows, '', '', 'noreason').map(r => r.id)).toEqual([1]);
  });
  it('passes everything through with no filters', () => { expect(filterRows(rows, '', '', 'all')).toHaveLength(2); });
});

describe('sortRows / visibleRows', () => {
  const rows = [t({id: 1, loom: 'D2', duration_sec: 100}), t({id: 2, loom: 'D10', duration_sec: 500})];
  it('sorts looms naturally (D2 before D10)', () => {
    const sort: Sort = {k: 'loom', dir: 1};
    expect(sortRows(rows, sort).map(r => r.id)).toEqual([1, 2]);
  });
  it('sorts by duration descending', () => {
    expect(sortRows(rows, {k: 'duration_sec', dir: -1}).map(r => r.id)).toEqual([2, 1]);
  });
  it('combines filtering and sorting', () => {
    expect(visibleRows(rows, '', 'D', 'all', {k: 'duration_sec', dir: -1}).map(r => r.id)).toEqual([2, 1]);
  });
});

describe('buildTiles', () => {
  it('summarises counts, downtime and top reasons', () => {
    const rows = [t({id: 1, reason: 'Электрика', duration_sec: 600, category_id: 'e'}),
      t({id: 2, reason: 'Электрика', duration_sec: 300, category_id: 'e'}),
      t({id: 3, reason: 'Без причины', duration_sec: 120, category_id: null})];
    const tiles = buildTiles(rows, 2);
    expect(tiles[0]).toEqual({label: 'Тикетов', value: 3});
    expect(tiles[1]).toEqual({label: 'Простой', value: dur(1020)});
    expect(tiles[2]).toEqual({label: 'Без причины', value: 1, sub: dur(120)});
    expect(tiles[3]).toEqual({label: 'Стоит сейчас', value: 2});
    expect(tiles[4]).toEqual({label: 'Электрика', value: dur(900), sub: '2'});
  });
  it('shows a dash when the live total is unavailable', () => {
    expect(buildTiles([], null)[3]).toEqual({label: 'Стоит сейчас', value: '—'});
  });
});

describe('shortTime', () => {
  it('keeps the day and time, dropping the seconds/year punctuation gap', () => {
    const ftime = () => '25.09.2026 08:15';
    expect(shortTime(ftime, 'anything')).toBe('25.09 08:15');
  });
});
