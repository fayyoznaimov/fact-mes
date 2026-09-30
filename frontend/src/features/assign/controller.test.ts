import { describe, expect, it, vi } from 'vitest';
import { AssignController } from './controller';
import type { FillResult, SavePayload } from './controller';
import type { Operator, ShiftDoc } from './model';

const operators: Operator[] = [
  {id: 1, code: 'O1', name: 'Иванова', role: 'operator', active: 1},
  {id: 2, code: 'O2', name: 'Сидорова', role: 'operator', active: 1},
  {id: 3, code: 'M1', name: 'Петрова', role: 'master', active: 1},
];

const doc: ShiftDoc = {
  day: '2026.09.25', shift: 'A', hours: '07:00–15:00',
  doc: {status: 'draft', foreman_id: null, note: 'привет', source: null, updated_by: null, updated_at: null, confirmed_by: null, confirmed_at: null},
  assignments: [{loom: 'D1', operator_id: 1}, {loom: 'D2', operator_id: null}],
  masters: [3], layout: {},
};

function setup(overrides: Partial<Parameters<typeof io>[0]> = {}) {
  const base = io(overrides);
  const controller = new AssignController(base, () => new Date('2026-09-25T09:00:00'));
  return {controller, io: base};
}
function io(overrides: Record<string, unknown> = {}) {
  return {
    requestDoc: vi.fn<() => Promise<ShiftDoc>>().mockResolvedValue(doc),
    requestWeekly: vi.fn<() => Promise<{docs: []}>>().mockResolvedValue({docs: []}),
    postSave: vi.fn<() => Promise<ShiftDoc>>().mockResolvedValue(doc),
    postConfirm: vi.fn<() => Promise<ShiftDoc>>().mockResolvedValue(doc),
    postFill: vi.fn<() => Promise<FillResult>>().mockResolvedValue({doc, found: 5, assigned: 4, from: '2026.09.24'}),
    operators: vi.fn<() => Operator[]>().mockReturnValue(operators),
    me: vi.fn().mockReturnValue(null),
    confirmTranslated: vi.fn().mockReturnValue(true),
    fday: (v: unknown) => String(v),
    ftime: (v: unknown) => String(v),
    openPrintWindow: vi.fn(),
    changed: vi.fn(), say: vi.fn(),
    ...overrides,
  };
}

describe('load', () => {
  it('defaults the day/shift from the clock on first load', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    expect(c.state.day).toBe('2026-09-25');
    expect(c.state.shift).toBe('A');
    expect(i.requestDoc).toHaveBeenCalledWith('2026.09.25', 'A', expect.anything());
  });
  it('seeds edits from the loaded document', async () => {
    const {controller: c} = setup();
    await c.load();
    expect(c.state.edits).toEqual({assignments: {D1: 1, D2: null}, masters: [3], foremanId: null, note: 'привет'});
  });
  it('forces the own master onto the selection for an unlocked doc', async () => {
    const {controller: c} = setup({me: vi.fn().mockReturnValue({role: 'master', employee_id: 9})});
    await c.load();
    expect(c.state.edits.masters).toEqual([9]);
  });
  it('fetches the weekly summary after loading the doc', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    expect(i.requestWeekly).toHaveBeenCalledWith('2026.09.19', '2026.09.25', expect.anything());
  });
  it('reports a load failure', async () => {
    const {controller: c, io: i} = setup();
    i.requestDoc.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(i.say).toHaveBeenCalledWith('Расстановка не загрузилась: нет сети', true);
  });
});

describe('setDay / setShift', () => {
  it('reloads for the new day', async () => {
    const {controller: c, io: i} = setup();
    c.setDay('2026-09-20');
    await Promise.resolve(); await Promise.resolve();
    expect(i.requestDoc).toHaveBeenCalledWith('2026.09.20', expect.any(String), expect.anything());
  });
});

describe('checked rows', () => {
  it('toggles a single loom', async () => {
    const {controller: c} = setup();
    await c.load();
    c.toggleChecked('D1');
    expect(c.state.checked.has('D1')).toBe(true);
    c.toggleChecked('D1');
    expect(c.state.checked.has('D1')).toBe(false);
  });
  it('checks all looms when editable, none when not', async () => {
    const {controller: c} = setup();
    await c.load();
    c.toggleAllChecked(true, true);
    expect(c.state.checked).toEqual(new Set(['D1', 'D2']));
    c.toggleAllChecked(false, false);
    expect(c.state.checked).toEqual(new Set(['D1', 'D2']));
    c.toggleAllChecked(false, true);
    expect(c.state.checked.size).toBe(0);
  });
});

describe('search and suggestions', () => {
  it('clears the bulk pick when the search text changes', async () => {
    const {controller: c} = setup();
    await c.load();
    c.pickOperator(operators[0]);
    expect(c.state.bulkId).toBe('1');
    c.setSearch('ив');
    expect(c.state.bulkId).toBe('');
    expect(c.state.suggestOpen).toBe(true);
  });
  it('moves through suggestions and wraps', async () => {
    const {controller: c} = setup();
    await c.load();
    c.setSearch('');
    c.moveSuggestion(1);
    expect(c.state.suggestIndex).toBe(0);
    c.moveSuggestion(1);
    expect(c.state.suggestIndex).toBe(1);
    c.moveSuggestion(1);
    expect(c.state.suggestIndex).toBe(0);
  });
  it('picks an operator by code and closes the list', async () => {
    const {controller: c} = setup();
    await c.load();
    c.pickOperator(operators[1]);
    expect(c.state.search).toBe('O2');
    expect(c.state.bulkId).toBe('2');
    expect(c.state.suggestOpen).toBe(false);
  });
});

describe('applyBulk', () => {
  it('assigns the picked operator to every checked loom and clears the checks', async () => {
    const {controller: c} = setup();
    await c.load();
    c.toggleChecked('D1'); c.toggleChecked('D2');
    c.pickOperator(operators[1]);
    c.applyBulk();
    expect(c.state.edits.assignments).toEqual({D1: 2, D2: 2});
    expect(c.state.checked.size).toBe(0);
  });
  it('clears the operator when nothing is picked and search is empty', async () => {
    const {controller: c} = setup();
    await c.load();
    c.toggleChecked('D1');
    c.applyBulk();
    expect(c.state.edits.assignments.D1).toBeNull();
  });
  it('refuses when text was typed but nothing picked', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    c.toggleChecked('D1');
    c.setSearch('ив');
    c.applyBulk();
    expect(i.say).toHaveBeenCalledWith('Выберите оператора из списка', true);
    expect(c.state.edits.assignments.D1).toBe(1);
  });
});

describe('setOperator / toggleMaster / setForeman / setNote', () => {
  it('updates a single loom assignment', async () => {
    const {controller: c} = setup();
    await c.load();
    c.setOperator('D2', 2);
    expect(c.state.edits.assignments.D2).toBe(2);
  });
  it('toggles a master in and out of the selection', async () => {
    const {controller: c} = setup();
    await c.load();
    c.toggleMaster(3);
    expect(c.state.edits.masters).toEqual([]);
    c.toggleMaster(3);
    expect(c.state.edits.masters).toEqual([3]);
  });
  it('sets the foreman and note', async () => {
    const {controller: c} = setup();
    await c.load();
    c.setForeman(4);
    c.setNote('пример');
    expect(c.state.edits.foremanId).toBe(4);
    expect(c.state.edits.note).toBe('пример');
  });
});

describe('save', () => {
  it('posts the current edits and reloads', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    c.setOperator('D2', 2);
    await c.save();
    expect(i.postSave).toHaveBeenCalledWith({
      day: '2026.09.25', shift: 'A',
      assignments: [{loom: 'D1', operator_id: 1}, {loom: 'D2', operator_id: 2}],
      masters: [3], foreman_id: null, note: 'привет',
    } satisfies SavePayload);
    expect(i.say).toHaveBeenCalledWith('Расстановка смены A сохранена');
    expect(i.requestDoc).toHaveBeenCalledTimes(2);
  });
  it('reports a failure', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    i.postSave.mockRejectedValueOnce(new Error('нет прав'));
    await c.save();
    expect(i.say).toHaveBeenCalledWith('Не сохранилось: нет прав', true);
  });
});

describe('confirm', () => {
  it('saves first, then confirms an unlocked doc', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    await c.confirm();
    expect(i.postSave).toHaveBeenCalledOnce();
    expect(i.postConfirm).toHaveBeenCalledWith('2026.09.25', 'A', true);
    expect(i.say).toHaveBeenCalledWith('Расстановка смены A утверждена');
  });
  it('reopens a confirmed doc without saving first', async () => {
    const locked: ShiftDoc = {...doc, doc: {...doc.doc!, status: 'confirmed'}};
    const {controller: c, io: i} = setup({requestDoc: vi.fn().mockResolvedValue(locked)});
    await c.load();
    await c.confirm();
    expect(i.postSave).not.toHaveBeenCalled();
    expect(i.postConfirm).toHaveBeenCalledWith('2026.09.25', 'A', false);
    expect(i.say).toHaveBeenCalledWith('Документ открыт для правки');
  });
});

describe('fill', () => {
  it('asks for confirmation and reports the FACT import result', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    await c.fill('fact');
    expect(i.confirmTranslated).toHaveBeenCalledWith('Заполнить расстановку по данным FACT? То, что на экране, заменится.');
    expect(i.postFill).toHaveBeenCalledWith('2026.09.25', 'A', 'fact');
    expect(i.say).toHaveBeenCalledWith('Из FACT: станков 5, назначено 4');
  });
  it('does nothing when the confirmation is declined', async () => {
    const {controller: c, io: i} = setup({confirmTranslated: vi.fn().mockReturnValue(false)});
    await c.load();
    await c.fill('prev');
    expect(i.postFill).not.toHaveBeenCalled();
  });
  it('reports copying the previous shift', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    await c.fill('prev');
    expect(i.say).toHaveBeenCalledWith('Взято из смены A за 2026.09.24');
  });
});

describe('print', () => {
  it('builds the document html from current edits and opens it', async () => {
    const {controller: c, io: i} = setup();
    await c.load();
    c.print();
    expect(i.openPrintWindow).toHaveBeenCalledOnce();
    expect(i.openPrintWindow.mock.calls[0][0]).toContain('Иванова (O1)');
  });
});
