import { afterEach, describe, expect, it, vi } from 'vitest';
import { LoomController } from './controller';
import type { Catalog, CatalogOrder, CellChange, LoomGrid } from './model';
import { key } from './model';

const grid = (): LoomGrid => ({
  days: ['2026.09.21', '2026.09.22', '2026.09.23'], last_fact_day: '2026.09.20', plan_from: '2026.09.21',
  plan_to: '2026.09.23', plan_loaded_at: null,
  looms: [
    {loom: 'D1', cells: {'2026.09.21': {order_no: '1557', product_code: 'P1'}}},
    {loom: 'D2', cells: {}},
  ],
});
const catalog = (): Catalog => ({orders: [
  {order_no: '1557', in_1c: true, in_plan: true, qty: 100, products: [
    {product_code: 'P1', qty: 100, done: 0, expected: 0}], cells: 1, done: 0, expected: 0, looms: ['D1']},
  {order_no: '2000', in_1c: true, in_plan: false, qty: 50, products: [
    {product_code: 'A', qty: 20, done: 0, expected: 0}, {product_code: 'B', qty: 30, done: 0, expected: 0}],
    cells: 0, done: 0, expected: 0, looms: []},
] as CatalogOrder[]});

function setup() {
  const io = {
    requestGrid: vi.fn<(f: string, t: string, s: AbortSignal) => Promise<LoomGrid>>(),
    requestCatalog: vi.fn<(s: AbortSignal) => Promise<Catalog>>(),
    postCells: vi.fn<(c: CellChange[]) => Promise<{ok: number; picked?: {ambiguous?: number; nomatch?: number}; report_days: string[]}>>(),
    uploadExcel: vi.fn(),
    changed: vi.fn(), say: vi.fn(), canEdit: vi.fn(() => true), dmy: (d: string) => d.slice(8, 10) + '.' + d.slice(5, 7),
    refreshPlan: vi.fn(),
  };
  io.requestGrid.mockResolvedValue(grid());
  io.requestCatalog.mockResolvedValue(catalog());
  const controller = new LoomController('2026.09.21', '2026.09.23', io);
  return {controller, io};
}
async function loaded() {
  const s = setup(); await s.controller.load(); return s;
}
afterEach(() => vi.restoreAllMocks());

describe('Loading the grid', () => {
  it('loads grid and catalog together and marks the state loaded', async () => {
    const {controller: c} = await loaded();
    expect(c.state.grid).toEqual(grid());
    expect(c.state.catalog).toEqual(catalog().orders);
    expect(c.state.loaded).toBe(true);
  });
  it('drops selection keys that no longer exist after reload', async () => {
    const {controller: c, io} = await loaded();
    c.click(key('D2', '2026.09.22'), {shift: false, ctrl: true});
    io.requestGrid.mockResolvedValueOnce({...grid(), looms: [grid().looms[0]]});
    await c.load();
    expect(c.state.selection.has(key('D2', '2026.09.22'))).toBe(false);
  });
  it('reports a failed load', async () => {
    const {controller: c, io} = setup();
    io.requestGrid.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('План цеха не загрузился: нет сети', true);
  });
});

describe('Selection', () => {
  it('replaces the selection on a plain click and sets the anchor', async () => {
    const {controller: c} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    expect(c.state.selection).toEqual(new Set([key('D1', '2026.09.21')]));
    expect(c.state.anchor).toBe(key('D1', '2026.09.21'));
    expect(c.state.focus).toBe('1557');
  });
  it('toggles membership on ctrl-click without touching other cells', async () => {
    const {controller: c} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.click(key('D2', '2026.09.22'), {shift: false, ctrl: true});
    expect(c.state.selection).toEqual(new Set([key('D1', '2026.09.21'), key('D2', '2026.09.22')]));
    c.click(key('D2', '2026.09.22'), {shift: false, ctrl: true});
    expect(c.state.selection).toEqual(new Set([key('D1', '2026.09.21')]));
  });
  it('selects a rectangle from the anchor on shift-click', async () => {
    const {controller: c} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.click(key('D2', '2026.09.22'), {shift: true, ctrl: false});
    expect(c.state.selection).toEqual(new Set([
      key('D1', '2026.09.21'), key('D1', '2026.09.22'), key('D2', '2026.09.21'), key('D2', '2026.09.22'),
    ]));
  });
  it('clears selection, anchor and focus on Escape-equivalent clearSelection', async () => {
    const {controller: c} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.clearSelection();
    expect(c.state.selection.size).toBe(0); expect(c.state.anchor).toBeNull(); expect(c.state.focus).toBeNull();
  });
});

describe('Applying changes, undo and permissions', () => {
  it('refuses to write without plan_edit', async () => {
    const {controller: c, io} = await loaded();
    io.canEdit.mockReturnValue(false);
    await c.applyChanges([{loom: 'D2', day: '2026.09.21', order_no: '2000'}]);
    expect(io.postCells).not.toHaveBeenCalled();
    expect(io.say).toHaveBeenCalledWith('Доступен только просмотр плана', true);
  });
  it('deduplicates changes to the same cell, keeping the last one', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    await c.applyChanges([
      {loom: 'D2', day: '2026.09.21', order_no: 'X'}, {loom: 'D2', day: '2026.09.21', order_no: 'Y'},
    ]);
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D2', day: '2026.09.21', order_no: 'Y'}]);
  });
  it('pushes an undo snapshot of the previous cell content and reloads on success', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    await c.applyChanges([{loom: 'D1', day: '2026.09.21', order_no: null}]);
    expect(c.state.undoStack).toHaveLength(1);
    expect(c.state.undoStack[0]).toEqual([{loom: 'D1', day: '2026.09.21',
      order_no: '1557', note: null, product: null, pile_yarn: null, product_code: 'P1', pick: null}]);
    expect(io.requestGrid).toHaveBeenCalledTimes(2); // initial load + reload after apply
  });
  it('reports ambiguous matches and report-day recalculation in the success message', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 2, picked: {ambiguous: 1}, report_days: ['2026.09.21']});
    await c.applyChanges([{loom: 'D2', day: '2026.09.21', order_no: '2000'}]);
    expect(io.say).toHaveBeenCalledWith(
      'Сохранено: клеток 2; изделие не подобралось в 1 — выберите двойным щелчком; отчёт пересчитывается за 21.09', true);
  });
  it('reports a failed save without touching the undo stack', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockRejectedValueOnce(new Error('занято'));
    await c.applyChanges([{loom: 'D2', day: '2026.09.21', order_no: '2000'}]);
    expect(io.say).toHaveBeenCalledWith('Не сохранилось: занято', true);
    expect(c.state.undoStack).toHaveLength(0);
  });
  it('undo pops the last snapshot and re-applies it as an undo (no new undo entry)', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValue({ok: 1, report_days: []});
    await c.applyChanges([{loom: 'D1', day: '2026.09.21', order_no: null}]);
    c.undo();
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalledTimes(2));
    expect(io.postCells).toHaveBeenLastCalledWith([{loom: 'D1', day: '2026.09.21',
      order_no: '1557', note: null, product: null, pile_yarn: null, product_code: 'P1', pick: null}]);
    expect(c.state.undoStack).toHaveLength(0);
  });
  it('deleteSelection clears every selected cell', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 2, report_days: []});
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.click(key('D2', '2026.09.22'), {shift: false, ctrl: true});
    c.deleteSelection();
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells.mock.calls[0][0]).toEqual(expect.arrayContaining([
      {loom: 'D1', day: '2026.09.21', order_no: null, note: null},
      {loom: 'D2', day: '2026.09.22', order_no: null, note: null},
    ]));
  });
});

describe('Placing an order on a cell', () => {
  it('places a single-product order across the assignment span', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.setSpan(2); c.setSkipSundays(false);
    c.place('1557', key('D2', '2026.09.21'));
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([
      {loom: 'D2', day: '2026.09.21', order_no: '1557', product_code: 'P1', note: null},
      {loom: 'D2', day: '2026.09.22', order_no: '1557', product_code: 'P1', note: null},
    ]);
  });
  it('opens the disambiguation dialog instead of applying for a multi-product order', async () => {
    const {controller: c, io} = await loaded();
    c.place('2000', key('D2', '2026.09.21'));
    expect(io.postCells).not.toHaveBeenCalled();
    expect(c.state.dialog).toEqual({keys: [key('D2', '2026.09.21')], forcedOrder: '2000'});
  });
  it('drops a specific product directly without opening the dialog', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.place('2000', key('D2', '2026.09.21'), 'B');
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D2', day: '2026.09.21', order_no: '2000', product_code: 'B', note: null}]);
  });
  it('fills the current multi-selection instead of the day-span when the dropped cell is selected', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 2, report_days: []});
    c.click(key('D2', '2026.09.21'), {shift: false, ctrl: false});
    c.click(key('D2', '2026.09.23'), {shift: false, ctrl: true});
    c.place('1557', key('D2', '2026.09.21'));
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith(expect.arrayContaining([
      {loom: 'D2', day: '2026.09.21', order_no: '1557', product_code: 'P1', note: null},
      {loom: 'D2', day: '2026.09.23', order_no: '1557', product_code: 'P1', note: null},
    ]));
  });
});

describe('Move/copy block and drag-drop', () => {
  it('moves a block one loom down, clearing the source', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.dropCellOnCell(key('D1', '2026.09.21'), key('D2', '2026.09.21'), true);
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith(expect.arrayContaining([
      {loom: 'D2', day: '2026.09.21', order_no: '1557', note: null, product: null, pile_yarn: null, product_code: 'P1', pick: null},
      {loom: 'D1', day: '2026.09.21', order_no: null, note: null},
    ]));
  });
  it('copies a block without clearing the source', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.dropCellOnCell(key('D1', '2026.09.21'), key('D2', '2026.09.21'), false);
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([
      {loom: 'D2', day: '2026.09.21', order_no: '1557', note: null, product: null, pile_yarn: null, product_code: 'P1', pick: null},
    ]);
  });
  it('does nothing when source and target are the same cell', async () => {
    const {controller: c, io} = await loaded();
    c.dropCellOnCell(key('D1', '2026.09.21'), key('D1', '2026.09.21'), true);
    expect(io.postCells).not.toHaveBeenCalled();
  });
  it('extends a multi-cell drag to the whole selection when the dragged cell is selected', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 2, report_days: []});
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.click(key('D1', '2026.09.22'), {shift: false, ctrl: true}); // cell has no content but is still part of the block
    c.dropCellOnCell(key('D1', '2026.09.21'), key('D2', '2026.09.21'), true);
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    const applied = io.postCells.mock.calls[0][0];
    expect(applied).toEqual(expect.arrayContaining([
      expect.objectContaining({loom: 'D2', day: '2026.09.21', order_no: '1557'}),
      expect.objectContaining({loom: 'D2', day: '2026.09.22'}),
    ]));
  });
});

describe('Copy/paste clipboard', () => {
  it('copies the selection and reports the count', async () => {
    const {controller: c, io} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.copySelection();
    expect(c.state.clipboard?.snap).toEqual([{k: key('D1', '2026.09.21'),
      c: {order_no: '1557', note: null, product: null, pile_yarn: null, product_code: 'P1', pick: null}}]);
    expect(io.say).toHaveBeenCalledWith('Скопировано клеток: 1');
  });
  it('pastes the clipboard aligned to the current selection', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.copySelection();
    c.click(key('D2', '2026.09.22'), {shift: false, ctrl: false});
    c.paste();
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([
      {loom: 'D2', day: '2026.09.22', order_no: '1557', note: null, product: null, pile_yarn: null, product_code: 'P1', pick: null},
    ]);
  });
  it('does nothing to paste with an empty clipboard', async () => {
    const {controller: c, io} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.paste();
    expect(io.postCells).not.toHaveBeenCalled();
  });
});

describe('Dialog', () => {
  it('opens for a single cell by default', async () => {
    const {controller: c} = await loaded();
    c.openDialog(key('D1', '2026.09.21'));
    expect(c.state.dialog).toEqual({keys: [key('D1', '2026.09.21')], forcedOrder: undefined});
  });
  it('opens for the whole selection when the clicked cell is part of it', async () => {
    const {controller: c} = await loaded();
    c.click(key('D1', '2026.09.21'), {shift: false, ctrl: false});
    c.click(key('D2', '2026.09.22'), {shift: false, ctrl: true});
    c.openDialog(key('D1', '2026.09.21'));
    expect(c.state.dialog?.keys).toEqual(expect.arrayContaining([key('D1', '2026.09.21'), key('D2', '2026.09.22')]));
  });
  it('is refused without edit permission', async () => {
    const {controller: c, io} = await loaded();
    io.canEdit.mockReturnValue(false);
    c.openDialog(key('D1', '2026.09.21'));
    expect(c.state.dialog).toBeNull();
  });
  it('cancel closes the dialog without applying anything', async () => {
    const {controller: c, io} = await loaded();
    c.openDialog(key('D1', '2026.09.21'));
    c.closeDialog();
    expect(c.state.dialog).toBeNull();
    expect(io.postCells).not.toHaveBeenCalled();
  });
  it('save applies the typed order/note/product to every dialog key', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.openDialog(key('D2', '2026.09.21'));
    c.submitDialog('save', ' 2000 ', ' пометка ', 'A');
    expect(c.state.dialog).toBeNull();
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D2', day: '2026.09.21', order_no: '2000', product_code: 'A', note: 'пометка'}]);
  });
  it('clear wipes the cell regardless of typed values', async () => {
    const {controller: c, io} = await loaded();
    io.postCells.mockResolvedValueOnce({ok: 1, report_days: []});
    c.openDialog(key('D1', '2026.09.21'));
    c.submitDialog('clear', '1557', 'x', 'P1');
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D1', day: '2026.09.21', order_no: null, product_code: null, note: null}]);
  });
});

describe('Order card interactions', () => {
  it('opens a multi-product order and sets focus when its card is clicked', async () => {
    const {controller: c} = await loaded();
    c.clickOrderCard('2000', false);
    expect(c.state.focus).toBe('2000');
    expect(c.state.open.has('2000')).toBe(true);
  });
  it('toggles focus off on a second click without touching open state', async () => {
    const {controller: c} = await loaded();
    c.clickOrderCard('1557', false);
    c.clickOrderCard('1557', false);
    expect(c.state.focus).toBeNull();
  });
  it('a product-line click only sets focus, never toggling open', async () => {
    const {controller: c} = await loaded();
    c.clickOrderCard('2000', true);
    expect(c.state.focus).toBe('2000');
    expect(c.state.open.has('2000')).toBe(false);
  });
  it('toggleOrderOpen flips membership', async () => {
    const {controller: c} = await loaded();
    c.toggleOrderOpen('2000');
    expect(c.state.open.has('2000')).toBe(true);
    c.toggleOrderOpen('2000');
    expect(c.state.open.has('2000')).toBe(false);
  });
});

describe('Excel upload', () => {
  it('uploads, reports the summary and asks for a full plan refresh', async () => {
    const {controller: c, io} = await loaded();
    io.uploadExcel.mockResolvedValueOnce({from: '2026-09-21', to: '2026-09-27', looms: 4, orders: [{order_no: '1'}, {order_no: '2'}], notes: []});
    const file = new File(['x'], 'plan.xlsx');
    await c.uploadExcel(file);
    expect(io.say).toHaveBeenCalledWith('План загружен: 21.09–27.09, станков 4, заказов 2');
    expect(io.refreshPlan).toHaveBeenCalledOnce();
    expect(c.state.uploading).toBe(false);
  });
  it('reports a failed upload without refreshing', async () => {
    const {controller: c, io} = await loaded();
    io.uploadExcel.mockRejectedValueOnce(new Error('неверный формат'));
    await c.uploadExcel(new File(['x'], 'plan.xlsx'));
    expect(io.say).toHaveBeenCalledWith('План не загрузился: неверный формат', true);
    expect(io.refreshPlan).not.toHaveBeenCalled();
  });
});
