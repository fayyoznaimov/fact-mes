import { describe, expect, it, vi } from 'vitest';
import { ManualController } from './controller';
import type { ManualResponse } from './model';

const response: ManualResponse = {
  from: '2026.09.01', to: '2026.09.24', group: 'day', installed: 8, days: 24, shifts: 60,
  columns: [], rows: [], totals: {key: 'итого', looms: 8, shed_eff: 90, time_eff: 80, stop_pct: 5, prod_eff: 85, stop_min: 100, explained_pct: 90, cats: {}},
};

function setup() {
  const io = {
    requestManual: vi.fn<() => Promise<ManualResponse>>().mockResolvedValue(response),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new ManualController(io);
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
  it('handles an empty day list', () => {
    const {controller: c} = setup();
    c.setDays([]);
    expect(c.state.from).toBe('');
    expect(c.state.to).toBe('');
  });
});

describe('setGroup', () => {
  it('changes the grouping and reloads immediately', async () => {
    const {controller: c, io} = setup();
    c.setDays(['2026.09.24', '2026.09.01']);
    c.setGroup('loom');
    await Promise.resolve(); await Promise.resolve();
    expect(c.state.group).toBe('loom');
    expect(io.requestManual).toHaveBeenCalledWith(expect.any(String), expect.any(String), 'loom', expect.anything());
  });
});

describe('load', () => {
  it('fetches the summary for the current range and grouping', async () => {
    const {controller: c, io} = setup();
    c.setDays(['2026.09.24', '2026.09.01']);
    await c.load();
    expect(io.requestManual).toHaveBeenCalledWith('2026.09.01', '2026.09.24', 'day', expect.anything());
    expect(c.state.data).toEqual(response);
  });
  it('drops a stale response', async () => {
    const {controller: c, io} = setup();
    let resolveFirst!: (v: ManualResponse) => void;
    io.requestManual.mockReturnValueOnce(new Promise(r => {resolveFirst = r;}));
    const first = c.load();
    io.requestManual.mockResolvedValueOnce({...response, installed: 99});
    const second = c.load();
    await second;
    resolveFirst(response);
    await first;
    expect(c.state.data?.installed).toBe(99);
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.requestManual.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Сводка ручных остановов не загрузилась: нет сети', true);
  });
});
