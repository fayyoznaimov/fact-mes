import { describe, expect, it, vi } from 'vitest';
import { PeopleController } from './controller';
import type { ImportFactResult, ImportResult, Operator } from './model';

const operators: Operator[] = [
  {id: 1, code: 'O1', name: 'Иванова', role: 'operator', active: 1},
  {id: 2, code: 'M1', name: 'Петрова', role: 'master', active: 1},
];

function setup(overrides: Record<string, unknown> = {}) {
  const io = {
    operators: vi.fn<() => Operator[]>().mockReturnValue(operators),
    requestOperators: vi.fn<() => Promise<{operators: Operator[]}>>().mockResolvedValue({operators}),
    postOperator: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    postDelete: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    postImport: vi.fn<() => Promise<ImportResult>>().mockResolvedValue({in_list: 1, added: 1, updated: 0, same: 0, repeats: 0, skipped: []}),
    postImportFact: vi.fn<() => Promise<ImportFactResult>>().mockResolvedValue({found: 5, added: 2, total: 10}),
    confirmTranslated: vi.fn().mockReturnValue(true),
    setOperators: vi.fn(),
    changed: vi.fn(), say: vi.fn(),
    ...overrides,
  };
  const controller = new PeopleController(io);
  return {controller, io};
}

describe('load', () => {
  it('seeds state from the already-loaded shared roster, without a network call', () => {
    const {controller: c, io} = setup();
    c.load();
    expect(c.state.operators).toEqual(operators);
    expect(io.requestOperators).not.toHaveBeenCalled();
  });
});

describe('add', () => {
  it('refuses without code or name', async () => {
    const {controller: c, io} = setup();
    c.setName('Кто-то');
    await c.add();
    expect(io.say).toHaveBeenCalledWith('Заполните код и имя', true);
    expect(io.postOperator).not.toHaveBeenCalled();
  });
  it('adds a new operator, clears the form and reloads', async () => {
    const {controller: c, io} = setup();
    c.setCode(' O9 '); c.setName(' Новая '); c.setRole('master');
    await c.add();
    expect(io.postOperator).toHaveBeenCalledWith({code: 'O9', name: 'Новая', role: 'master'});
    expect(c.state.form.code).toBe('');
    expect(c.state.form.name).toBe('');
    expect(io.say).toHaveBeenCalledWith('Добавлен: Новая');
    expect(io.requestOperators).toHaveBeenCalledOnce();
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    io.postOperator.mockRejectedValueOnce(new Error('код занят'));
    c.setCode('O1'); c.setName('Иванова');
    await c.add();
    expect(io.say).toHaveBeenCalledWith('Не добавился: код занят', true);
  });
});

describe('setOperatorRole', () => {
  it('saves the new role and updates the local list', async () => {
    const {controller: c, io} = setup();
    await c.load();
    await c.setOperatorRole(1, 'foreman');
    expect(io.postOperator).toHaveBeenCalledWith({id: 1, code: 'O1', name: 'Иванова', role: 'foreman', active: true});
    expect(c.state.operators.find(o => o.id === 1)?.role).toBe('foreman');
    expect(io.say).toHaveBeenCalledWith('Иванова: foreman');
  });
  it('leaves the role unchanged on failure', async () => {
    const {controller: c, io} = setup();
    await c.load();
    io.postOperator.mockRejectedValueOnce(new Error('нет прав'));
    await c.setOperatorRole(1, 'foreman');
    expect(c.state.operators.find(o => o.id === 1)?.role).toBe('operator');
    expect(io.say).toHaveBeenCalledWith('Не сохранилось: нет прав', true);
  });
});

describe('remove', () => {
  it('asks for confirmation before deleting', async () => {
    const {controller: c, io} = setup({confirmTranslated: vi.fn().mockReturnValue(false)});
    await c.remove(1);
    expect(io.postDelete).not.toHaveBeenCalled();
  });
  it('deletes and reloads on confirmation', async () => {
    const {controller: c, io} = setup();
    await c.remove(1);
    expect(io.postDelete).toHaveBeenCalledWith(1);
    expect(io.requestOperators).toHaveBeenCalledOnce();
  });
});

describe('importPaste', () => {
  it('refuses an empty paste', async () => {
    const {controller: c, io} = setup();
    await c.importPaste();
    expect(io.say).toHaveBeenCalledWith('Вставьте список', true);
  });
  it('imports, clears the textarea and shows the summary', async () => {
    const {controller: c, io} = setup();
    c.setPasteText('код\tимя\n1\tИванов');
    await c.importPaste();
    expect(io.postImport).toHaveBeenCalledWith('код\tимя\n1\tИванов');
    expect(c.state.pasteText).toBe('');
    expect(c.state.pasteResult).toBe('В списке 1 человек: добавлено 1, обновлено 0, без изменений 0');
  });
});

describe('importFact', () => {
  it('imports from FACT and reports the summary', async () => {
    const {controller: c, io} = setup();
    await c.importFact();
    expect(io.say).toHaveBeenCalledWith('Найдено имён в FACT: 5, добавлено новых: 2, всего в справочнике: 10');
  });
});
