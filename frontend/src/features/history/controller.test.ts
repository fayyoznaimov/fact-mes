import { describe, expect, it, vi } from 'vitest';
import { HistoryController } from './controller';
import type { MachineHistory, SignalsResponse } from './model';

const row = (loom: string) => ({
  loom, events: [], segments: [], totals: {stop: 0, estimated_run: 0, unknown: 0, future: 0},
  shift_checks: [], invalid_records: 0, overlap_sec: 0, tickets: [],
});
const mh: MachineHistory = {
  day: '2026-09-25', period: 'day', start: 0, end: 86400, timezone: '+05:00', generated_at: 86400,
  catalog: ['D1', 'D2'], available_from: null, available_to: '2026-09-25', rows: [row('D1'), row('D2')],
};
const signals: SignalsResponse = {loom: 'D1', start: 0, end: 86400, note: '', samples: [{at: 1, values: {state: 'run'}}]};

function setup() {
  const io = {
    requestHistory: vi.fn<() => Promise<MachineHistory>>().mockResolvedValue(mh),
    requestSignals: vi.fn<() => Promise<SignalsResponse>>().mockResolvedValue(signals),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new HistoryController(io);
  return {controller, io};
}

describe('load', () => {
  it('fetches the timeline for the current day/period/loom filter', async () => {
    const {controller: c, io} = setup();
    c.setDay('2026-09-25'); c.setPeriod('A');
    await c.load();
    expect(io.requestHistory).toHaveBeenCalledWith('2026-09-25', 'A', '', expect.anything());
    expect(c.state.data).toEqual(mh);
    expect(c.state.catalog).toEqual(['D1', 'D2']);
  });
  it('expands a row selector using the current catalog', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.setLoomSelect('row:D');
    await Promise.resolve(); await Promise.resolve();
    expect(io.requestHistory).toHaveBeenLastCalledWith(expect.any(String), expect.any(String), 'D1,D2', expect.anything());
  });
  it('auto-selects and loads signals when there is exactly one row', async () => {
    const {controller: c, io} = setup();
    io.requestHistory.mockResolvedValueOnce({...mh, rows: [row('D1')]});
    await c.load();
    expect(c.state.selectedRow).toBe(0);
    expect(io.requestSignals).toHaveBeenCalledWith('D1', mh.day, mh.period, expect.anything());
  });
  it('does not auto-select when there are multiple rows', async () => {
    const {controller: c, io} = setup();
    await c.load();
    expect(c.state.selectedRow).toBeNull();
    expect(io.requestSignals).not.toHaveBeenCalled();
  });
  it('reports a failure and clears data while keeping the catalog', async () => {
    const {controller: c, io} = setup();
    await c.load();
    io.requestHistory.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(c.state.data).toBeNull();
    expect(c.state.error).toBe('История не загрузилась: нет сети');
    expect(c.state.catalog).toEqual(['D1', 'D2']);
  });
  it('drops a stale response', async () => {
    const {controller: c, io} = setup();
    let resolveFirst!: (v: MachineHistory) => void;
    io.requestHistory.mockReturnValueOnce(new Promise(r => {resolveFirst = r;}));
    const first = c.load();
    io.requestHistory.mockResolvedValueOnce({...mh, day: 'second'});
    const second = c.load();
    await second;
    resolveFirst(mh);
    await first;
    expect(c.state.data?.day).toBe('second');
  });
});

describe('selectRow', () => {
  it('selects a row, resets the page/detail and loads its signals', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.setPage(3);
    c.selectRow(1);
    expect(c.state.selectedRow).toBe(1);
    expect(c.state.page).toBe(0);
    expect(c.state.detail).toBeNull();
    await Promise.resolve(); await Promise.resolve();
    expect(io.requestSignals).toHaveBeenCalledWith('D2', mh.day, mh.period, expect.anything());
  });
  it('exposes the selected row via currentRow()', async () => {
    const {controller: c} = setup();
    await c.load();
    c.selectRow(1);
    expect(c.currentRow()?.loom).toBe('D2');
  });
});

describe('clear', () => {
  it('drops the loaded timeline and selection, keeping the catalog for the select box', async () => {
    const {controller: c} = setup();
    await c.load();
    c.selectRow(0);
    c.clear();
    expect(c.state.data).toBeNull();
    expect(c.state.selectedRow).toBeNull();
    expect(c.state.catalog).toEqual(['D1', 'D2']);
  });
});

describe('event/ticket detail', () => {
  it('tracks which event or ticket is shown', () => {
    const {controller: c} = setup();
    c.showEventDetail(2);
    expect(c.state.detail).toEqual({kind: 'event', index: 2});
    c.showTicketDetail(0);
    expect(c.state.detail).toEqual({kind: 'ticket', index: 0});
  });
});

describe('signals', () => {
  it('picks "state" as the default key when present', async () => {
    const {controller: c} = setup();
    await c.load();
    c.selectRow(0);
    await Promise.resolve(); await Promise.resolve();
    expect(c.state.signals.selectedKey).toBe('state');
    expect(c.state.signals.data).toEqual(signals);
  });
  it('falls back to the first key when "state" is absent', async () => {
    const {controller: c, io} = setup();
    io.requestSignals.mockResolvedValueOnce({...signals, samples: [{at: 1, values: {rpm: 5}}]});
    await c.load();
    c.selectRow(0);
    await Promise.resolve(); await Promise.resolve();
    expect(c.state.signals.selectedKey).toBe('rpm');
  });
  it('reports a signals load failure', async () => {
    const {controller: c, io} = setup();
    io.requestSignals.mockRejectedValueOnce(new Error('нет данных'));
    await c.load();
    c.selectRow(0);
    await Promise.resolve(); await Promise.resolve();
    expect(c.state.signals.error).toBe('нет данных');
  });
  it('changes the selected signal key', async () => {
    const {controller: c} = setup();
    await c.load();
    c.selectRow(0);
    await Promise.resolve(); await Promise.resolve();
    c.setSignalKey('rpm');
    expect(c.state.signals.selectedKey).toBe('rpm');
  });
});
