import { describe, expect, it, vi } from 'vitest';
import { SalaryController } from './controller';
import type { SalaryResponse } from './model';

const salary: SalaryResponse = {
  day: '2026-09-24', shift: 'A', rate: 287, rate_unit: 'kpick',
  operators: [{operator_id: 1, code: 'O1', name: 'Иванова', looms: ['D1'], loom_count: 1,
    picks: 5000, kpicks: 5, salary: 1435, effic: 90, weft_ct: 1, top_ct: 0, warp_ct: 0,
    weft_cmpx: 2, warp_cmpx: 0, wait_min: 3, manual_ct: 0}],
  masters: [{id: 9, code: 'M1', name: 'Петрова'}],
  unassigned_looms: [],
  looms: [{loom: 'D1', style: 'X1', picks: 5000, kpicks: 5, salary: 1435, effic: 90,
    weft_ct: 1, warp_ct: 0, wait_min: 3, operator_id: 1, operator: 'Иванова'}],
  totals: {picks: 5000, kpicks: 5, salary: 1435, salary_all: 1435, unassigned_salary: 0, looms: 1, assigned: 1},
};

function setup() {
  const io = {
    requestSalary: vi.fn<() => Promise<SalaryResponse>>().mockResolvedValue(salary),
    postAssignOne: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    postAssignCopy: vi.fn<() => Promise<{copied: number; from: string | null}>>().mockResolvedValue({copied: 1, from: '2026-09-23.C'}),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new SalaryController(io);
  return {controller, io};
}

describe('setShifts', () => {
  it('defaults to the first (most recent) shift when none is selected yet', () => {
    const {controller: c} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}, {day: '2026-09-23', shift: 'C'}]);
    expect(c.state.shiftIndex).toBe(0);
  });
  it('keeps the current index if it is still valid', () => {
    const {controller: c} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}, {day: '2026-09-23', shift: 'C'}]);
    c.setShiftIndex(1);
    c.setShifts([{day: '2026-09-25', shift: 'B'}, {day: '2026-09-24', shift: 'A'}, {day: '2026-09-23', shift: 'C'}]);
    expect(c.state.shiftIndex).toBe(1);
  });
  it('falls back to -1 when the list is empty', () => {
    const {controller: c} = setup();
    c.setShifts([]);
    expect(c.state.shiftIndex).toBe(-1);
  });
});

describe('load', () => {
  it('fetches salary for the selected shift', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    await c.load();
    expect(io.requestSalary).toHaveBeenCalledWith('2026-09-24', 'A', expect.anything());
    expect(c.state.data).toEqual(salary);
  });
  it('does nothing when no shift is selected', async () => {
    const {controller: c, io} = setup();
    await c.load();
    expect(io.requestSalary).not.toHaveBeenCalled();
  });
  it('drops a stale response that resolves after a newer request started', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    let resolveFirst!: (v: SalaryResponse) => void;
    io.requestSalary.mockReturnValueOnce(new Promise(r => {resolveFirst = r;}));
    const first = c.load();
    io.requestSalary.mockResolvedValueOnce({...salary, totals: {...salary.totals, salary: 999}});
    const second = c.load();
    await second;
    resolveFirst(salary);
    await first;
    expect(c.state.data?.totals.salary).toBe(999);
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    io.requestSalary.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Зарплата не посчиталась: нет сети', true);
  });
});

describe('copy', () => {
  it('copies the previous shift assignment and reloads', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    await c.copy();
    expect(io.postAssignCopy).toHaveBeenCalledWith('2026-09-24', 'A');
    expect(io.say).toHaveBeenCalledWith('Перенесено со смены 2026-09-23.C: станков 1');
    expect(io.requestSalary).toHaveBeenCalledOnce();
  });
  it('reports when there is nothing to copy', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    io.postAssignCopy.mockResolvedValueOnce({copied: 0, from: null});
    await c.copy();
    expect(io.say).toHaveBeenCalledWith('Не нашлось смены с расстановкой — назначьте вручную');
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    io.postAssignCopy.mockRejectedValueOnce(new Error('нет прав'));
    await c.copy();
    expect(io.say).toHaveBeenCalledWith('Не перенеслось: нет прав', true);
  });
});

describe('assign', () => {
  it('assigns an operator to a loom and reloads', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    await c.assign('D1', 2);
    expect(io.postAssignOne).toHaveBeenCalledWith('2026-09-24', 'A', 'D1', 2);
    expect(io.say).toHaveBeenCalledWith('D1: оператор назначен');
    expect(io.requestSalary).toHaveBeenCalledOnce();
  });
  it('reports removal with a different message when cleared', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    await c.assign('D1', null);
    expect(io.say).toHaveBeenCalledWith('D1: снят');
  });
  it('reports a failure without reloading', async () => {
    const {controller: c, io} = setup();
    c.setShifts([{day: '2026-09-24', shift: 'A'}]);
    io.postAssignOne.mockRejectedValueOnce(new Error('нет прав'));
    await c.assign('D1', 2);
    expect(io.say).toHaveBeenCalledWith('Не сохранилось: нет прав', true);
    expect(io.requestSalary).not.toHaveBeenCalled();
  });
});
