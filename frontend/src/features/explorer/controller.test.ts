import { describe, expect, it, vi } from 'vitest';
import { ExplorerController } from './controller';
import type { ExplorerResponse } from './model';

const response: ExplorerResponse = {
  totals: {eff: 80, run_h: 100, stop_h: 25, mpicks: 1.5, rows: 10, idle_shifts: 1},
  causes: {'Уток': 5, 'Основа': 2},
  by_loom: [{loom: 'D1', eff: 80, kpicks: 100, weft_ct: 5, weft_cmpx: 1, warp_ct: 2, top_ct: 0,
    manual_ct: 0, manual_h: 0, wait_h: 0, shifts: 10, idle_shifts: 0, warp_out_h: 0, other_h: 0, power_h: 0}],
};

function setup() {
  const io = {
    requestExplorer: vi.fn<() => Promise<ExplorerResponse>>().mockResolvedValue(response),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new ExplorerController(io);
  return {controller, io};
}

describe('setDays', () => {
  it('defaults to a 30-day window ending on the most recent day', () => {
    const {controller: c} = setup();
    const days = Array.from({length: 40}, (_, i) => `day${i}`);
    c.setDays(days);
    expect(c.state.from).toBe('day29');
    expect(c.state.to).toBe('day0');
  });
});

describe('toggleShift', () => {
  it('toggles shifts but keeps at least one selected', () => {
    const {controller: c} = setup();
    c.toggleShift('A');
    expect(c.state.shifts).toEqual(new Set(['B', 'C']));
    c.toggleShift('B'); c.toggleShift('C');
    expect(c.state.shifts).toEqual(new Set(['C']));
  });
});

describe('load', () => {
  it('orders the range and joins selected shifts before requesting', async () => {
    const {controller: c, io} = setup();
    c.setDays(['2026.09.25', '2026.09.24']);
    // reversed on purpose to check ordering
    c.setFrom('2026.09.25'); c.setTo('2026.09.24');
    c.toggleShift('B');
    await c.load();
    expect(io.requestExplorer).toHaveBeenCalledWith('2026.09.24', '2026.09.25', 'AC', 'all', expect.anything());
    expect(c.state.data).toEqual(response);
  });
  it('drops a stale response', async () => {
    const {controller: c, io} = setup();
    let resolveFirst!: (v: ExplorerResponse) => void;
    io.requestExplorer.mockReturnValueOnce(new Promise(r => {resolveFirst = r;}));
    const first = c.load();
    io.requestExplorer.mockResolvedValueOnce({...response, totals: {...response.totals, eff: 99}});
    const second = c.load();
    await second;
    resolveFirst(response);
    await first;
    expect(c.state.data?.totals.eff).toBe(99);
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    io.requestExplorer.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Простои не загрузились: нет сети', true);
  });
});
