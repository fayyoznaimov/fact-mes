import { describe, expect, it, vi } from 'vitest';
import { WalkController } from './controller';
import type { WalkResponse } from './model';

const response: WalkResponse = {
  day: '2026.09.24', shift: 'B',
  rows: [{loom: 'D1', style: 'D327', eff: 80, stop_min: 20, weft_ct: 1, top_ct: 0, warp_ct: 0, manual_ct: 0, wait_min: 5, idle: false, main: 'уток', main_min: 10}],
};

function setup() {
  const io = {
    requestWalk: vi.fn<() => Promise<WalkResponse>>().mockResolvedValue(response),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new WalkController(io);
  return {controller, io};
}

describe('setShifts', () => {
  it('defaults to the last completed shift (index 1)', () => {
    const {controller: c} = setup();
    c.setShifts([{day: '2026.09.25', shift: 'A'}, {day: '2026.09.24', shift: 'C'}, {day: '2026.09.24', shift: 'B'}]);
    expect(c.state.shiftIndex).toBe(1);
  });
  it('falls back to index 0 with only one shift', () => {
    const {controller: c} = setup();
    c.setShifts([{day: '2026.09.25', shift: 'A'}]);
    expect(c.state.shiftIndex).toBe(0);
  });
  it('falls back to -1 with no shifts', () => {
    const {controller: c} = setup();
    c.setShifts([]);
    expect(c.state.shiftIndex).toBe(-1);
  });
  it('keeps a valid current index', () => {
    const {controller: c} = setup();
    c.setShifts([{day: '2026.09.25', shift: 'A'}, {day: '2026.09.24', shift: 'C'}]);
    c.setShiftIndex(0);
    c.setShifts([{day: '2026.09.26', shift: 'A'}, {day: '2026.09.25', shift: 'A'}, {day: '2026.09.24', shift: 'C'}]);
    expect(c.state.shiftIndex).toBe(0);
  });
});

describe('load', () => {
  it('fetches the walk list for the selected shift', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026.09.25', shift: 'A'}, {day: '2026.09.24', shift: 'B'}]);
    await c.load();
    expect(io.requestWalk).toHaveBeenCalledWith('2026.09.24', 'B', expect.anything());
    expect(c.state.data).toEqual(response);
  });
  it('does nothing without a selected shift', async () => {
    const {controller: c, io} = setup();
    await c.load();
    expect(io.requestWalk).not.toHaveBeenCalled();
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026.09.25', shift: 'A'}]);
    io.requestWalk.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Обход не загрузился: нет сети', true);
  });
});
