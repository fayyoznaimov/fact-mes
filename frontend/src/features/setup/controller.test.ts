import { describe, expect, it, vi } from 'vitest';
import { SetupController } from './controller';
import type { YarnRow } from './bridge';
import type { SetupGridResponse } from './model';

const yarns: YarnRow[] = [
  {id: 1, name: '16/1 SPUN', key: '16/1SPUN', kind: 'pile', active: true},
];

const grid: SetupGridResponse = {
  day: '2026.09.24', report_day: '2026.09.24',
  rows: [
    {loom: 'D1', cloth: 'X1', design: 'D144', values: {design: 'D144', gsm: 500, pile_yarn: '16/1 SPUN'}, manual: {}},
    {loom: 'D2', cloth: 'X1', design: 'D144', values: {design: 'D144', gsm: 500, pile_yarn: '16/1 SPUN'}, manual: {design: true}},
  ],
};

function setup() {
  const io = {
    requestGrid: vi.fn<() => Promise<SetupGridResponse>>().mockResolvedValue(grid),
    postYarn: vi.fn<(b: unknown) => Promise<{name: string}>>().mockResolvedValue({name: 'X'}),
    postYarnUpdate: vi.fn<(b: unknown) => Promise<unknown>>().mockResolvedValue({ok: true}),
    uploadYarns: vi.fn(),
    confirmSetup: vi.fn<(p: unknown) => Promise<{id: number; number: string} | null>>().mockResolvedValue({id: 1, number: 'C-1'}),
    changed: vi.fn(), say: vi.fn(),
    yarns: vi.fn(() => yarns),
    refreshYarns: vi.fn().mockResolvedValue(undefined),
    confirmDiscard: vi.fn(() => true),
  };
  const controller = new SetupController(io);
  return {controller, io};
}

describe('load', () => {
  it('loads the grid, derives columns and snapshots original values', async () => {
    const {controller: c} = setup();
    c.setDay('2026-09-24');
    await c.load();
    expect(c.state.loaded).toBe(true);
    expect(c.state.rows).toHaveLength(2);
    expect(c.state.cells[0].design).toBe('D144');
    expect(c.state.original).toEqual(c.state.cells);
    expect(c.state.reportDay).toBe('2026.09.24');
  });
  it('asks before discarding unsaved edits on reload, and respects a decline', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.typeCell(0, 0, 'changed');
    io.confirmDiscard.mockReturnValueOnce(false);
    await c.load();
    expect(io.requestGrid).toHaveBeenCalledTimes(1);
    expect(c.state.cells[0].design).toBe('changed');
  });
  it('force-reload skips the discard prompt', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.typeCell(0, 0, 'changed');
    await c.load(true);
    expect(io.confirmDiscard).not.toHaveBeenCalled();
    expect(c.state.cells[0].design).toBe('D144');
  });
});

describe('cell editing', () => {
  it('typeCell marks the row dirty without touching yarn casing', async () => {
    const {controller: c} = setup();
    await c.load();
    c.typeCell(0, 5, '16/1spun');
    expect(c.state.cells[0].pile_yarn).toBe('16/1spun');
    expect(c.isDirty()).toBe(true);
  });
  it('commitCell canonicalizes a yarn cell that matches an active yarn by key', async () => {
    const {controller: c} = setup();
    await c.load();
    c.typeCell(0, 5, '16/1spun');
    c.commitCell(0, 5);
    expect(c.state.cells[0].pile_yarn).toBe('16/1 SPUN');
  });
  it('commitCell leaves non-yarn columns untouched', async () => {
    const {controller: c} = setup();
    await c.load();
    c.typeCell(0, 0, 'xyz');
    c.commitCell(0, 0);
    expect(c.state.cells[0].design).toBe('xyz');
  });
});

describe('bulk actions on picked rows', () => {
  it('fillFocusToPicked requires a focus and at least one picked row', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.fillFocusToPicked();
    expect(io.say).toHaveBeenCalledWith('Сначала встаньте в ячейку, значение которой нужно протянуть', true);
    c.setFocus(0, 0);
    c.fillFocusToPicked();
    expect(io.say).toHaveBeenCalledWith('Отметьте станки галочками слева', true);
  });
  it('fillFocusToPicked copies the focused cell to every picked row, canonicalizing yarn', async () => {
    const {controller: c} = setup();
    await c.load();
    c.setFocus(0, 5);
    c.typeCell(0, 5, '16/1spun');
    c.togglePick(1);
    c.fillFocusToPicked();
    expect(c.state.cells[1].pile_yarn).toBe('16/1 SPUN');
  });
  it('copyRowToPicked copies every column of the focused row, excluding the focus row itself', async () => {
    const {controller: c} = setup();
    await c.load();
    c.setFocus(0, 0);
    c.typeCell(0, 0, 'D999');
    c.togglePick(0); c.togglePick(1);
    c.copyRowToPicked();
    expect(c.state.cells[1].design).toBe('D999');
  });
  it('markSameCloth picks every row sharing the focused row\'s cloth code', async () => {
    const {controller: c} = setup();
    await c.load();
    c.setFocus(0, 0);
    c.markSameCloth();
    expect(c.state.picked).toEqual(new Set([0, 1]));
  });
});

describe('paste', () => {
  it('distributes a block paste starting at the focused cell', async () => {
    const {controller: c} = setup();
    await c.load();
    const n = c.paste(0, 0, 'AAA\tGGG\nBBB\tHHH');
    expect(n).toBe(4);
    expect(c.state.cells[0]).toMatchObject({design: 'AAA', gsm: 'GGG'});
    expect(c.state.cells[1]).toMatchObject({design: 'BBB', gsm: 'HHH'});
  });
});

describe('save', () => {
  it('reports no changes without calling the API', async () => {
    const {controller: c, io} = setup();
    await c.load();
    await c.save();
    expect(io.say).toHaveBeenCalledWith('Изменений нет');
    expect(io.confirmSetup).not.toHaveBeenCalled();
  });
  it('requires the setup time before posting', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.setTime('');
    c.typeCell(0, 0, 'D999');
    await c.save();
    expect(io.say).toHaveBeenCalledWith('Укажите время начала заправки', true);
    expect(io.confirmSetup).not.toHaveBeenCalled();
  });
  it('posts only the changed rows with their full current values, then reloads', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.typeCell(0, 0, 'D999');
    await c.save();
    expect(io.confirmSetup).toHaveBeenCalledWith(expect.objectContaining({
      rows: [{loom: 'D1', values: expect.objectContaining({design: 'D999'})}],
    }));
    expect(io.requestGrid).toHaveBeenCalledTimes(2); // initial load + reload after save
  });
  it('offers to add unknown yarn to the dictionary before saving', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.typeCell(0, 5, 'brand new yarn');
    await c.save();
    expect(io.confirmDiscard).toHaveBeenCalledWith(expect.stringContaining('BRAND NEW YARN'));
    expect(io.postYarn).toHaveBeenCalledWith({name: 'BRAND NEW YARN'});
  });
  it('does not save when the user declines adding the unknown yarn', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.typeCell(0, 5, 'brand new yarn');
    io.confirmDiscard.mockReturnValueOnce(false);
    await c.save();
    expect(io.confirmSetup).not.toHaveBeenCalled();
  });
});

describe('yarn dictionary', () => {
  it('addYarn rejects an empty name', async () => {
    const {controller: c, io} = setup();
    await c.addYarn('', '');
    expect(io.say).toHaveBeenCalledWith('Напишите название пряжи', true);
    expect(io.postYarn).not.toHaveBeenCalled();
  });
  it('addYarn posts, reports and refreshes the dictionary', async () => {
    const {controller: c, io} = setup();
    io.postYarn.mockResolvedValueOnce({name: '20/2 SPUN'});
    await c.addYarn('20/2 spun', 'pile');
    expect(io.postYarn).toHaveBeenCalledWith({name: '20/2 spun', kind: 'pile'});
    expect(io.say).toHaveBeenCalledWith('Добавлена пряжа «20/2 SPUN»');
    expect(io.refreshYarns).toHaveBeenCalledOnce();
  });
});
