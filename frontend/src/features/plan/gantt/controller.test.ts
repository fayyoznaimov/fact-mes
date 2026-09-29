import { afterEach, describe, expect, it, vi } from 'vitest';
import { GanttController, TimelineController } from './controller';
import type { GanttData, TimelineData } from './model';
import { monday } from './model';

const data = (over: Partial<GanttData> = {}): GanttData => ({from: '2026.09.21', to: '2026.09.27',
  days: ['2026.09.21'], now: '2026-09-24T10:00:00', last_fact_day: '2026.09.24', schedule: [], looms: [], ...over});
function setupGantt() {
  const io = {request: vi.fn<(from: string, to: string, signal: AbortSignal) => Promise<GanttData>>(), changed: vi.fn(), say: vi.fn()};
  return {controller: new GanttController(io), io};
}
afterEach(() => vi.restoreAllMocks());

describe('GanttController', () => {
  it('starts on the current week with 7 days and no data', () => {
    const {controller: c} = setupGantt();
    expect(c.state).toEqual({from: monday(), days: 7, group: '', data: null});
  });
  it('loads using the current from/days window', async () => {
    const {controller: c, io} = setupGantt();
    io.request.mockResolvedValueOnce(data());
    await c.load();
    expect(io.request).toHaveBeenCalledWith(monday(), expect.any(String), expect.anything());
    expect(c.state.data).toEqual(data());
  });
  it('setDays reloads with the new span', async () => {
    const {controller: c, io} = setupGantt();
    io.request.mockResolvedValue(data());
    c.setDays(14);
    await Promise.resolve(); await Promise.resolve();
    expect(c.state.days).toBe(14);
    expect(io.request).toHaveBeenCalled();
  });
  it('setGroup filters without a fetch', () => {
    const {controller: c, io} = setupGantt();
    c.setGroup('Dobby');
    expect(c.state.group).toBe('Dobby');
    expect(io.request).not.toHaveBeenCalled();
  });
  it('prev/next/today move the window and reload', async () => {
    const {controller: c, io} = setupGantt();
    io.request.mockResolvedValue(data());
    c.prev(); await Promise.resolve(); await Promise.resolve();
    const from1 = c.state.from;
    c.next(); await Promise.resolve(); await Promise.resolve();
    expect(c.state.from).not.toBe(from1);
    c.today(); await Promise.resolve(); await Promise.resolve();
    expect(c.state.from).toBe(monday());
  });
  it('reports a failed load without clearing existing data', async () => {
    const {controller: c, io} = setupGantt();
    io.request.mockResolvedValueOnce(data());
    await c.load();
    io.request.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Ганта не загрузилась: нет сети', true);
    expect(c.state.data).toEqual(data());
  });
  it('loadOnce fetches only when no data is present yet', async () => {
    const {controller: c, io} = setupGantt();
    io.request.mockResolvedValue(data());
    c.loadOnce();
    await Promise.resolve(); await Promise.resolve();
    expect(io.request).toHaveBeenCalledOnce();
    c.loadOnce();
    expect(io.request).toHaveBeenCalledOnce();
  });
});

const tlData = (): TimelineData => ({loom: 'D1', from: '2026-09-24T07:00:00', to: '2026-09-24T15:00:00',
  events: [], by_cause: [], stop_sec: 0, shift: null});
function setupTimeline() {
  const io = {request: vi.fn<(loom: string, from: string, to: string, signal: AbortSignal) => Promise<TimelineData>>(), changed: vi.fn(), say: vi.fn()};
  return {controller: new TimelineController(io), io};
}

describe('TimelineController', () => {
  it('opens and stores the fetched shift', async () => {
    const {controller: c, io} = setupTimeline();
    io.request.mockResolvedValueOnce(tlData());
    await c.open('D1', '2026-09-24T07:00:00', '2026-09-24T15:00:00');
    expect(c.state).toEqual({loom: 'D1', a: '2026-09-24T07:00:00', b: '2026-09-24T15:00:00', data: tlData()});
  });
  it('steps by whole hours from the currently open shift', async () => {
    const {controller: c, io} = setupTimeline();
    io.request.mockResolvedValue(tlData());
    await c.open('D1', '2026-09-24T07:00:00', '2026-09-24T15:00:00');
    c.step(8);
    await Promise.resolve(); await Promise.resolve();
    expect(io.request).toHaveBeenLastCalledWith('D1', '2026-09-24T15:00:00', '2026-09-24T23:00:00', expect.anything());
  });
  it('does nothing when stepping with nothing open', () => {
    const {controller: c, io} = setupTimeline();
    c.step(8);
    expect(io.request).not.toHaveBeenCalled();
  });
  it('close clears the state', async () => {
    const {controller: c, io} = setupTimeline();
    io.request.mockResolvedValueOnce(tlData());
    await c.open('D1', '2026-09-24T07:00:00', '2026-09-24T15:00:00');
    c.close();
    expect(c.state).toBeNull();
  });
  it('reports a failed open', async () => {
    const {controller: c, io} = setupTimeline();
    io.request.mockRejectedValueOnce(new Error('403'));
    await c.open('D1', '2026-09-24T07:00:00', '2026-09-24T15:00:00');
    expect(io.say).toHaveBeenCalledWith('Остановы не загрузились: 403', true);
    expect(c.state).toBeNull();
  });
});
