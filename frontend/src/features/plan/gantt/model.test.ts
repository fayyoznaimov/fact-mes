import { describe, expect, it } from 'vitest';
import {
  addDays, eventBarView, eventRowStart, factBarView, isoOf, lastWorkedFact, monday,
  planBarView, rangeText, tickLabels, timeScale, timelineSummary, timelineTitle, weekdayOf, ymd,
} from './model';
import type { FactBar, GanttLoom, PlanBar, TimelineData } from './model';

const nf = (x: unknown, d = 0) => x == null || x === '' ? '' : Number(x).toLocaleString('ru-RU', {minimumFractionDigits: d, maximumFractionDigits: d});
const dmy = (d: string) => d ? d.slice(8, 10) + '.' + d.slice(5, 7) : '';

describe('timeScale', () => {
  const {pos, wid} = timeScale('2026-09-20T07:00:00', '2026-09-27T07:00:00');
  it('clamps positions to [0,100]', () => {
    expect(pos('2026-09-15T00:00:00')).toBe(0);
    expect(pos('2026-10-01T00:00:00')).toBe(100);
    expect(pos('2026-09-23T19:00:00')).toBeCloseTo(50, 5);
  });
  it('enforces a minimum visible width of 0.2%', () => {
    expect(wid('2026-09-20T07:00:00', '2026-09-20T07:00:01')).toBe(0.2);
  });
});

describe('planBarView', () => {
  it('labels an order bar with its design and quantity, and hues it by order number', () => {
    const b: PlanBar = {order_no: '1557', design: 'D144', start: '2026-09-20', end: '2026-09-25', days: 5, qty_plan: 5200};
    const v = planBarView(b, dmy, nf);
    expect(v.label).toBe(`1557 D144 · ≈${nf(5200)}`);
    expect(v.tip).toBe(`заказ 1557; с 20.09, 5 дн.; план ≈ ${nf(5200)} шт`);
    expect(v.hasOrder).toBe(true);
    expect(v.hue).not.toBeNull();
  });
  it('renders a note-only bar without an order and without a hue', () => {
    const b: PlanBar = {note: 'Praborka', start: '2026-09-20', end: '2026-09-21', days: 1};
    const v = planBarView(b, dmy, nf);
    expect(v.label).toBe('Praborka');
    expect(v.hasOrder).toBe(false);
    expect(v.hue).toBeNull();
  });
});

describe('factBarView', () => {
  it('marks idle shifts distinctly from worked ones', () => {
    expect(factBarView({start: '', end: '', shift: 'A', towels: 0, eff: 0, run_min: 0, idle: true}, dmy, nf).cls).toBe('idle');
    expect(factBarView({start: '', end: '', shift: 'A', towels: 100, eff: 65, run_min: 400, cloth: 'X1'}, dmy, nf).cls).toBe('e-red');
    expect(factBarView({start: '', end: '', shift: 'A', towels: 100, eff: 75, run_min: 400}, dmy, nf).cls).toBe('e-yel');
    expect(factBarView({start: '', end: '', shift: 'A', towels: 100, eff: 95, run_min: 400}, dmy, nf).cls).toBe('e-ok');
  });
});

describe('rangeText / weekdayOf / lastWorkedFact', () => {
  it('formats the visible range with the last fact day', () => {
    expect(rangeText({from: '2026-09-20', to: '2026-09-27', last_fact_day: '2026-09-24'} as never, dmy))
      .toBe('20.09 07:00 — 27.09 07:00; факт по 24.09');
    expect(rangeText({from: '2026-09-20', to: '2026-09-27', last_fact_day: null} as never, dmy))
      .toBe('20.09 07:00 — 27.09 07:00; факт по —');
  });
  it('names the weekday for a given day', () => { expect(weekdayOf('2026-09-20')).toBe('вс'); });
  it('picks the most recent non-idle shift', () => {
    const loom: GanttLoom = {loom: 'D1', group: 'Dobby', plan: [], fact: [
      {start: 'a', end: 'b', shift: 'A', towels: 10, eff: 80, run_min: 400} as FactBar,
      {start: 'c', end: 'd', shift: 'B', towels: 0, eff: 0, run_min: 0, idle: true} as FactBar,
    ]};
    expect(lastWorkedFact(loom)?.shift).toBe('A');
    expect(lastWorkedFact({...loom, fact: [{start: 'x', end: 'y', shift: 'C', towels: 0, eff: 0, run_min: 0, idle: true}]})).toBeUndefined();
  });
});

describe('timeline formatting', () => {
  const data: TimelineData = {loom: 'D1', from: '2026-09-24T07:00:00', to: '2026-09-24T15:00:00',
    events: [{start: '2026-09-24T08:00:00', dur: 120, cause: 'Weft', cause_ru: 'Уток'}], by_cause: [],
    stop_sec: 120, shift: {id: '2026-09-24:A', effic: 82.5, run_min: 420, stop_min: 60, cloth: 'X144', worked: true}};
  it('titles the dialog with the shift id and time range', () => {
    expect(timelineTitle('D1', data, dmy)).toBe('D1: смена A, 24.09 07:00–15:00');
  });
  it('summarises efficiency and stop time', () => {
    expect(timelineSummary(data, nf)).toBe('КПД 82,5 %, работал 420 мин, стоял 60 мин; остановов 1, 2 мин; ткань X144');
  });
  it('falls back to a plain summary with no shift', () => {
    expect(timelineSummary({...data, shift: null}, nf)).toBe('остановов 1, 2 мин');
  });
  it('positions an event bar within the timeline span', () => {
    const t0 = Date.parse(data.from), span = Date.parse(data.to) - t0;
    const v = eventBarView(data.events[0], t0, span);
    expect(v.left).toBeCloseTo(12.5, 5);
    expect(v.color).toBe('#df5656');
  });
  it('builds one tick per hour boundary', () => {
    const t0 = Date.parse(data.from), span = Date.parse(data.to) - t0;
    const ticks = tickLabels(t0, span);
    expect(ticks[0].text).toBe('07:00');
    expect(ticks[ticks.length - 1].text).toBe('15:00');
  });
  it('prefixes the row date only when the event predates the window', () => {
    expect(eventRowStart({start: '2026-09-23T23:50:00', dur: 5, cause: 'Other', cause_ru: ''}, data.from, dmy)).toBe('23.09 23:50:00');
    expect(eventRowStart(data.events[0], data.from, dmy)).toBe('08:00:00');
  });
});

describe('period date helpers', () => {
  it('adds days across a month boundary', () => { expect(addDays('2026.09.30', 1)).toBe('2026.10.01'); });
  it('formats a date as ymd', () => { expect(ymd(new Date(2026, 8, 5))).toBe('2026.09.05'); });
  it('finds this week\'s Monday', () => { expect(monday()).toMatch(/^\d{4}\.\d{2}\.\d{2}$/); });
  it('formats a Date as a local ISO-ish string', () => { expect(isoOf(new Date(2026, 8, 24, 7, 5))).toBe('2026-09-24T07:05:00'); });
});
