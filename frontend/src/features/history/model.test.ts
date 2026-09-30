import { describe, expect, it } from 'vitest';
import {
  buildGridHtml, chartPolylines, chartRange, chartValues, flattenSignalValues, loomGroups, loomsParam,
  mhColor, mhDuration, mhPack, mhSegTitle, mhStop, mhTime, pageEvents, pageRangeText, signalKeys, statusText,
} from './model';
import type { FlatSample, MachineHistory } from './model';

describe('mhDuration', () => {
  it('formats hours, minutes and seconds', () => { expect(mhDuration(3725)).toBe('1 ч 2 мин 5 с'); });
  it('formats a short duration', () => { expect(mhDuration(65)).toBe('0 ч 1 мин 5 с'); });
});

describe('mhTime', () => {
  it('shifts unix seconds by +5:00 and prints HH:MM:SS', () => {
    // 2026-09-25T04:00:00Z + 5h = 09:00:00 shop time
    const t = Date.UTC(2026, 8, 25, 4, 0, 0) / 1000;
    expect(mhTime(t)).toBe('09:00:00');
  });
  it('prefixes the day and month when full', () => {
    const t = Date.UTC(2026, 8, 25, 4, 0, 0) / 1000;
    expect(mhTime(t, true)).toBe('25.09 09:00:00');
  });
});

describe('mhColor', () => {
  it('maps a known cause', () => { expect(mhColor('Weft')).toBe('#df5656'); });
  it('falls back to "Other" for unknown causes', () => { expect(mhColor('???')).toBe(mhColor('Other')); });
});

describe('mhSegTitle / mhStop', () => {
  it('describes an observed-run segment', () => {
    expect(mhSegTitle({kind: 'observed_run', start: 0, end: 3600})).toContain('Работа');
  });
  it('describes an observed-stop segment with reason', () => {
    expect(mhSegTitle({kind: 'observed_stop', reason: 'Уток', start: 0, end: 60})).toBe('Стоит: Уток · по снимкам FACT · 01.01 05:00:00 — 01.01 05:01:00');
  });
  it('is empty for non-observed kinds', () => { expect(mhSegTitle({kind: 'stop', start: 0, end: 60})).toBe(''); });
  it('sums logged and observed stop time', () => {
    expect(mhStop({stop: 100, estimated_run: 0, unknown: 0, future: 0, observed_stop: 50})).toBe(150);
  });
});

describe('mhPack', () => {
  it('merges adjacent items of the same key within the gap', () => {
    const items = [{start: 0, end: 10, duration_sec: 10}, {start: 12, end: 20, duration_sec: 8}];
    const packed = mhPack(items, 5, () => 'x');
    expect(packed).toHaveLength(1);
    expect(packed[0]).toMatchObject({start: 0, end: 20, n: 2, sec: 18});
  });
  it('keeps items separate when the gap between them is too large', () => {
    const items = [{start: 0, end: 10, duration_sec: 10}, {start: 100, end: 110, duration_sec: 10}];
    expect(mhPack(items, 5, () => 'x')).toHaveLength(2);
  });
  it('keeps items separate when the key differs', () => {
    const items = [{start: 0, end: 10, cause: 'a'}, {start: 11, end: 20, cause: 'b'}];
    expect(mhPack(items, 5, x => x.cause)).toHaveLength(2);
  });
});

describe('loomGroups / loomsParam', () => {
  const catalog = ['D1', 'D2', 'D14', 'J1', 'J2'];
  it('groups looms by their letter prefix', () => { expect(loomGroups(catalog)).toEqual(['D', 'J']); });
  it('expands a row selector to the matching looms', () => { expect(loomsParam('row:D', catalog)).toBe('D1,D2,D14'); });
  it('passes a single loom through unchanged', () => { expect(loomsParam('D1', catalog)).toBe('D1'); });
});

describe('pageEvents / pageRangeText', () => {
  const events = Array.from({length: 120}, (_, i) => ({start: i} as never));
  it('slices 50 events per page', () => {
    expect(pageEvents(events, 0)).toHaveLength(50);
    expect(pageEvents(events, 2)).toHaveLength(20);
  });
  it('formats the visible range text', () => {
    expect(pageRangeText(120, 0)).toBe('1–50 из 120');
    expect(pageRangeText(120, 2)).toBe('101–120 из 120');
    expect(pageRangeText(0, 0)).toBe('0–0 из 0');
  });
});

describe('flattenSignalValues / signalKeys', () => {
  it('flattens nested objects with dot-joined keys', () => {
    expect(flattenSignalValues({state: 'run', details: {remaining_m: 5}})).toEqual({state: 'run', 'details.remaining_m': 5});
  });
  it('collects the union of keys across samples, sorted', () => {
    const samples: FlatSample[] = [{at: 1, flat: {b: 1}}, {at: 2, flat: {a: 1, c: 1}}];
    expect(signalKeys(samples)).toEqual(['a', 'b', 'c']);
  });
});

describe('chartValues / chartRange / chartPolylines', () => {
  const samples: FlatSample[] = [{at: 10, flat: {rpm: 100}}, {at: 20, flat: {rpm: 150}}, {at: 30, flat: {rpm: null}}];
  it('extracts values for a plain key using the sample time', () => {
    expect(chartValues(samples, 'rpm')).toEqual([{at: 10, v: 100}, {at: 20, v: 150}, {at: 30, v: null}]);
  });
  it('uses details_at for nested detail keys when present', () => {
    const s: FlatSample[] = [{at: 10, flat: {'details.remaining_m': 5}, }];
    (s[0] as unknown as {flat: Record<string, unknown>}).flat.details_at = 12;
    expect(chartValues(s, 'details.remaining_m')).toEqual([{at: 12, v: 5}]);
  });
  it('computes the numeric range, ignoring non-numeric points', () => {
    expect(chartRange(chartValues(samples, 'rpm'))).toEqual({lo: 100, hi: 150});
  });
  it('returns null range with no numeric points', () => {
    expect(chartRange([{at: 1, v: null}])).toBeNull();
  });
  it('builds one polyline per continuous run, breaking on gaps or missing data', () => {
    const lines = chartPolylines(chartValues(samples, 'rpm'), 0, 100);
    expect(lines).toHaveLength(1); // null point ends the chunk with nothing after it
    expect(lines[0].split(' ')).toHaveLength(2);
  });
  it('splits into separate polylines across a >120s gap', () => {
    const gapped: FlatSample[] = [{at: 0, flat: {v: 1}}, {at: 200, flat: {v: 2}}];
    const lines = chartPolylines(chartValues(gapped, 'v'), 0, 400);
    expect(lines).toHaveLength(2);
  });
});

describe('statusText', () => {
  const base: MachineHistory = {
    day: '2026-09-25', period: 'day', start: 0, end: 86400, timezone: '+05:00', generated_at: 0,
    catalog: [], available_from: null, available_to: '2026-09-25', rows: [],
  };
  it('summarises station and event counts', () => {
    const mh: MachineHistory = {...base, rows: [
      {loom: 'D1', events: [{} as never, {} as never], segments: [], totals: {stop: 0, estimated_run: 0, unknown: 0, future: 0}, shift_checks: [], invalid_records: 0, overlap_sec: 0, tickets: []},
    ]};
    expect(statusText(mh)).toBe('2026-09-25 · Станки: 1 · Остановки: 2 · Журнал доступен по 2026-09-25. ');
  });
  it('flags stations with unknown gaps', () => {
    const mh: MachineHistory = {...base, rows: [
      {loom: 'D1', events: [], segments: [], totals: {stop: 0, estimated_run: 0, unknown: 100, future: 0}, shift_checks: [], invalid_records: 0, overlap_sec: 0, tickets: []},
    ]};
    expect(statusText(mh)).toContain('Станки с промежутками без подтверждённого состояния: 1.');
  });
});

describe('buildGridHtml', () => {
  const mh: MachineHistory = {
    day: '2026-09-25', period: 'day', start: 0, end: 86400, timezone: '+05:00', generated_at: 86400,
    catalog: ['D1'], available_from: null, available_to: '2026-09-25',
    rows: [{
      loom: 'D1',
      events: [{start: 100, end: 200, cause: 'Weft', reason: 'Уток', code: null, shift: 'A', style: null, response_sec: null, duration_sec: 100}],
      segments: [{start: 0, end: 100, kind: 'estimated_run'}, {start: 100, end: 200, kind: 'stop'}, {start: 200, end: 86400, kind: 'estimated_run'}],
      totals: {stop: 100, estimated_run: 86300, unknown: 0, future: 0},
      shift_checks: [], invalid_records: 0, overlap_sec: 0,
      tickets: [{id: 5, start: 100, end: 200, open: false, reason: 'Электрика', comment: '', cause: null}],
    }],
  };
  it('renders one row per loom with a data-row index and svg', () => {
    const html = buildGridHtml(mh);
    expect(html).toContain('data-row="0"');
    expect(html).toContain('data-loom="0"');
    expect(html).toContain('<svg');
    expect(html).toContain('D1');
  });
  it('renders the event as a colored rect with a data-event index', () => {
    const html = buildGridHtml(mh);
    expect(html).toContain('data-event="0"');
    expect(html).toContain('fill="#df5656"');
  });
  it('renders the ticket as a data-ticket rect', () => {
    const html = buildGridHtml(mh);
    expect(html).toContain('data-ticket="0"');
    expect(html).toContain('Тикет 5');
  });
  it('renders the hour axis and total stop time', () => {
    const html = buildGridHtml(mh);
    expect(html).toContain('mh-axis');
    expect(html).toContain('mh-total');
  });
  it('escapes html-sensitive characters in titles', () => {
    const withXss: MachineHistory = {...mh, rows: [{...mh.rows[0], loom: '<x>'}]};
    const html = buildGridHtml(withXss);
    expect(html).toContain('&lt;x&gt;');
    expect(html).not.toContain('<x>История');
  });
});
