import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Gantt } from './Gantt';
import type { GanttState, TimelineState } from './controller';
import type { GanttData, TimelineData } from './model';
import { ganttMarkup, ganttOutput, legacyFormatters, legacyGantt, legacyTimeline, timelineOutput } from '../../../test/legacyPlan';
import type { PlanBridge } from '../bridge';

const gData: GanttData = {
  from: '2026-09-21T07:00:00', to: '2026-09-24T07:00:00',
  days: ['2026.09.21', '2026.09.22', '2026.09.23'], now: '2026-09-22T10:00:00', last_fact_day: '2026.09.22',
  schedule: [
    {shift: 'A', start: '2026-09-21T07:00:00', end: '2026-09-21T15:00:00'},
    {shift: 'B', start: '2026-09-21T15:00:00', end: '2026-09-21T23:00:00'},
    {shift: 'C', start: '2026-09-21T23:00:00', end: '2026-09-22T07:00:00', off: true},
  ],
  looms: [
    {loom: 'D1', group: 'Dobby', plan: [{order_no: '1557', design: 'D144', start: '2026-09-21', end: '2026-09-23', days: 2, qty_plan: 5200}],
      fact: [{start: '2026-09-21T07:00:00', end: '2026-09-21T15:00:00', shift: 'A', cloth: 'X144', towels: 300, eff: 88, run_min: 420}]},
    {loom: 'J1', group: 'Jakart Bonas', plan: [{note: 'Praborka', start: '2026-09-21', end: '2026-09-22', days: 1}],
      fact: [{start: '2026-09-21T07:00:00', end: '2026-09-21T15:00:00', shift: 'A', towels: 0, eff: 0, run_min: 0, idle: true}]},
  ],
};

function bridge(): PlanBridge {
  const f = legacyFormatters();
  return {can: () => true, say: vi.fn(), expire: vi.fn(), refreshPlan: vi.fn(), esc: f.esc, nf: f.nf, fday: f.fday, ftime: f.ftime, dmy: f.dmy};
}
function mount(state: GanttState, timeline: TimelineState | null, overrides: Partial<{
  setDays: ReturnType<typeof vi.fn>; setGroup: ReturnType<typeof vi.fn>; prev: ReturnType<typeof vi.fn>;
  next: ReturnType<typeof vi.fn>; today: ReturnType<typeof vi.fn>; openTimeline: ReturnType<typeof vi.fn>;
  stepTimeline: ReturnType<typeof vi.fn>; closeTimeline: ReturnType<typeof vi.fn>;
}> = {}) {
  document.body.innerHTML = ganttMarkup;
  const barEl = document.querySelector('#gt-days')!.closest('.bar') as HTMLElement;
  const wrapEl = document.querySelector('#gt-wrap') as HTMLElement;
  const dialog = document.querySelector('#gt-dlg') as HTMLDialogElement;
  [barEl, wrapEl, dialog].forEach(el => el.replaceChildren());
  const props = {
    setDays: vi.fn(), setGroup: vi.fn(), prev: vi.fn(), next: vi.fn(), today: vi.fn(),
    openTimeline: vi.fn(), stepTimeline: vi.fn(), closeTimeline: vi.fn(), ...overrides,
  };
  render(<Gantt barEl={barEl} wrapEl={wrapEl} dialog={dialog} state={state} timeline={timeline} bridge={bridge()} {...props}/>);
  return {barEl, wrapEl, dialog, ...props};
}
beforeEach(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {configurable: true, value(this: HTMLDialogElement) {this.open = true;}},
    close: {configurable: true, value(this: HTMLDialogElement) {if (this.open) {this.open = false; this.dispatchEvent(new Event('close'));}}},
  });
});
afterEach(() => {cleanup(); document.body.innerHTML = '';});

describe('Parity with the original Gantt canvas', () => {
  it('renders names, axis, background, now-line and bars exactly like the legacy renderer', () => {
    mount({from: gData.from, days: 3, group: '', data: gData}, null);
    expect(ganttOutput(document)).toEqual(ganttOutput(legacyGantt(gData)));
  });
  it('filters by loom group without changing the underlying data', () => {
    mount({from: gData.from, days: 3, group: 'Jakart Bonas', data: gData}, null);
    expect(ganttOutput(document)).toEqual(ganttOutput(legacyGantt(gData, 'Jakart Bonas')));
  });
  it('shows the legacy loading placeholder with no data yet', () => {
    mount({from: gData.from, days: 7, group: '', data: null}, null);
    expect(document.querySelector('#gt-wrap p')?.textContent).toBe('Загружаю…');
  });
});

describe('Parity with the original stop-timeline dialog', () => {
  const tlData: TimelineData = {loom: 'D1', from: '2026-09-21T07:00:00', to: '2026-09-21T15:00:00',
    events: [{start: '2026-09-21T08:00:00', dur: 90, cause: 'Weft', cause_ru: 'Уток'}],
    by_cause: [{cause: 'Weft', cause_ru: 'Уток', n: 1, sec: 90}], stop_sec: 90,
    shift: {id: '2026-09-21:A', effic: 88, run_min: 420, stop_min: 60, cloth: 'X144', worked: true}};
  it('renders title, summary, bars, ticks, legend and the stop table exactly like the legacy dialog', async () => {
    mount({from: gData.from, days: 3, group: '', data: gData},
      {loom: 'D1', a: tlData.from, b: tlData.to, data: tlData});
    expect(timelineOutput(document)).toEqual(timelineOutput(await legacyTimeline('D1', tlData.from, tlData.to, tlData)));
  });
  it('shows the legacy empty-events state', async () => {
    const empty = {...tlData, events: []};
    mount({from: gData.from, days: 3, group: '', data: gData}, {loom: 'D1', a: empty.from, b: empty.to, data: empty});
    expect(timelineOutput(document)).toEqual(timelineOutput(await legacyTimeline('D1', empty.from, empty.to, empty)));
  });
});

describe('Interactions', () => {
  it('opens the stop dialog when a fact bar is clicked', () => {
    const {wrapEl, openTimeline} = mount({from: gData.from, days: 3, group: '', data: gData}, null);
    fireEvent.click(wrapEl.querySelector('.gt-lane.f .gt-b')!);
    expect(openTimeline).toHaveBeenCalledWith('D1', '2026-09-21T07:00:00', '2026-09-21T15:00:00');
  });
  it('opens the stop dialog with Enter on a focused fact bar', () => {
    const {wrapEl, openTimeline} = mount({from: gData.from, days: 3, group: '', data: gData}, null);
    fireEvent.keyDown(wrapEl.querySelector('.gt-lane.f .gt-b')!, {key: 'Enter'});
    expect(openTimeline).toHaveBeenCalledOnce();
  });
  it('opens the last worked shift when a loom name is clicked', () => {
    const {wrapEl, openTimeline} = mount({from: gData.from, days: 3, group: '', data: gData}, null);
    fireEvent.click(wrapEl.querySelector('.gt-loom')!);
    expect(openTimeline).toHaveBeenCalledWith('D1', '2026-09-21T07:00:00', '2026-09-21T15:00:00');
  });
  it('reports no worked shifts for an all-idle loom name click', () => {
    const {wrapEl, openTimeline} = mount({from: gData.from, days: 3, group: '', data: gData}, null, {});
    const buttons = wrapEl.querySelectorAll('.gt-loom');
    fireEvent.click(buttons[1]);
    expect(openTimeline).not.toHaveBeenCalled();
  });
  it('changes the day count and the group filter', () => {
    const {barEl, setDays, setGroup} = mount({from: gData.from, days: 7, group: '', data: gData}, null);
    fireEvent.change(barEl.querySelector('#gt-days')!, {target: {value: '14'}});
    expect(setDays).toHaveBeenCalledWith(14);
    fireEvent.change(barEl.querySelector('#gt-group')!, {target: {value: 'Dobby'}});
    expect(setGroup).toHaveBeenCalledWith('Dobby');
  });
  it('navigates the period with prev/today/next', () => {
    const {barEl, prev, today, next} = mount({from: gData.from, days: 7, group: '', data: gData}, null);
    const [prevBtn, todayBtn, nextBtn] = barEl.querySelectorAll('button');
    fireEvent.click(prevBtn); fireEvent.click(todayBtn); fireEvent.click(nextBtn);
    expect(prev).toHaveBeenCalledOnce(); expect(today).toHaveBeenCalledOnce(); expect(next).toHaveBeenCalledOnce();
  });
  it('steps the open shift by 8 hours in each direction', () => {
    const tlData: TimelineData = {loom: 'D1', from: '2026-09-21T07:00:00', to: '2026-09-21T15:00:00',
      events: [], by_cause: [], stop_sec: 0, shift: null};
    const {dialog, stepTimeline} = mount({from: gData.from, days: 3, group: '', data: gData},
      {loom: 'D1', a: tlData.from, b: tlData.to, data: tlData});
    const buttons = dialog.querySelectorAll('button');
    fireEvent.click(buttons[0]); fireEvent.click(buttons[1]);
    expect(stepTimeline).toHaveBeenCalledWith(-8);
    expect(stepTimeline).toHaveBeenCalledWith(8);
  });
  it('closes via the native dialog close event', () => {
    const tlData: TimelineData = {loom: 'D1', from: '2026-09-21T07:00:00', to: '2026-09-21T15:00:00',
      events: [], by_cause: [], stop_sec: 0, shift: null};
    const {dialog, closeTimeline} = mount({from: gData.from, days: 3, group: '', data: gData},
      {loom: 'D1', a: tlData.from, b: tlData.to, data: tlData});
    expect(dialog.open).toBe(true);
    dialog.close();
    expect(closeTimeline).toHaveBeenCalledOnce();
  });
});
