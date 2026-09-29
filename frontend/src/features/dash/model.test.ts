import { describe, expect, it } from 'vitest';
import type { DashRow, DashTotals, ForecastEvent, Mismatch } from './model';
import { articleOptions, dur, filterRows, inText, noteText, splitForecast, warnSummary, yarnEntries } from './model';

describe('dur', () => {
  it('formats seconds under an hour as minutes only', () => { expect(dur(125)).toBe('2 мин'); });
  it('formats an hour+ duration with zero-padded minutes', () => { expect(dur(3725)).toBe('1 ч 02 мин'); });
  it('clamps negative input to zero', () => { expect(dur(-5)).toBe('0 мин'); });
});

const row = (over: Partial<DashRow> = {}): DashRow => ({
  loom: 'D1', state: 'run', kpicks: 1, towels: 1, weft_ct: 0, warp_ct: 0, top_ct: 0, ...over,
});

describe('filterRows', () => {
  const rows: DashRow[] = [row({loom: 'D1', state: 'run'}), row({loom: 'D2', state: 'stop'}),
    row({loom: 'D3', state: 'run', ticket: {reason: 'обрыв'}})];
  it('"all" keeps everything', () => { expect(filterRows(rows, 'all')).toHaveLength(3); });
  it('"stop" keeps only stopped looms', () => { expect(filterRows(rows, 'stop').map(r => r.loom)).toEqual(['D2']); });
  it('"ticket" keeps only looms with an open ticket', () => { expect(filterRows(rows, 'ticket').map(r => r.loom)).toEqual(['D3']); });
});

describe('noteText', () => {
  it('adds the "not everyone matched" caveat only when plan coverage exceeds product coverage', () => {
    const base: DashTotals = {running: 0, stopped: 0, with_ticket: 0, kpicks: 0, weft_ct: 0, warp_ct: 0, top_ct: 0,
      with_plan: 10, looms: 12, with_product: 10, with_operator: 8};
    expect(noteText(base)).not.toContain('у остальных заказ');
    expect(noteText({...base, with_product: 7})).toContain('у остальных заказ');
  });
});

describe('warnSummary', () => {
  it('counts mismatches', () => {
    const m: Mismatch[] = [{loom: 'D1', text: 'x'}, {loom: 'D2', text: 'y'}];
    expect(warnSummary(m)).toBe('На станке не то, что в плане: 2 — проверьте код ткани на станке или план');
  });
});

describe('yarnEntries', () => {
  it('combines yarn name with its lot when present', () => {
    const r = row({yarn: {pile: '16/1 SPUN'}, lots: {pile: 'L7'}});
    expect(yarnEntries(r, {pile: 'Ворс'})).toEqual([{label: 'Ворс', text: '16/1 SPUN л.L7'}]);
  });
  it('omits the lot suffix when there is none', () => {
    const r = row({yarn: {pile: '16/1 SPUN'}});
    expect(yarnEntries(r, {pile: 'Ворс'})).toEqual([{label: 'Ворс', text: '16/1 SPUN'}]);
  });
  it('falls back to the slot key when there is no title', () => {
    const r = row({yarn: {weft1: '20/2'}});
    expect(yarnEntries(r, {})).toEqual([{label: 'weft1', text: '20/2'}]);
  });
});

describe('articleOptions', () => {
  it('always offers an empty "not set" option first', () => {
    expect(articleOptions(row(), [])[0]).toEqual({value: '', label: '— не задано —', starred: false});
  });
  it('stars candidates from the row and sorts the rest alphabetically', () => {
    const opts = articleOptions(row({candidates: ['B100']}), ['A200', 'B100']);
    expect(opts.slice(1)).toEqual([
      {value: 'A200', label: 'A200', starred: false},
      {value: 'B100', label: 'B100', starred: true},
    ]);
  });
  it('deduplicates a candidate that also appears in the general article list', () => {
    const opts = articleOptions(row({candidates: ['A200']}), ['A200']);
    expect(opts).toHaveLength(2); // empty option + A200 once
  });
});

describe('splitForecast / inText', () => {
  const events: ForecastEvent[] = [
    {at: '14:00', in_min: 200, loom: 'D1', what: 'съём'},
    {at: '13:10', in_min: 40, loom: 'D2', what: 'сход навоя'},
  ];
  it('splits into soon (<=120min) and later, sorted by time remaining', () => {
    const {soon, later} = splitForecast(events);
    expect(soon.map(e => e.loom)).toEqual(['D2']);
    expect(later.map(e => e.loom)).toEqual(['D1']);
  });
  it('formats minutes under an hour plainly, and hours+minutes otherwise', () => {
    expect(inText(40)).toBe('40 мин');
    expect(inText(200)).toBe('3 ч 20 мин');
  });
});
