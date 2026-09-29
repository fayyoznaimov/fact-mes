import { useState } from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Loom } from './Loom';
import { LoomController } from './controller';
import type { Catalog, CatalogOrder, CellChange, LoomGrid } from './model';
import { key } from './model';
import {
  legacyFormatters, legacyLoomGrid, legacyOrderCard, legacyOrdersList, loomGridOutput,
  loomMarkup, orderCardOutput, ordersListOutput,
} from '../../../test/legacyPlan';
import type { PlanBridge } from '../bridge';

const grid = (): LoomGrid => ({
  days: ['2026.09.21', '2026.09.22'], last_fact_day: '2026.09.21', plan_from: '2026.09.20', plan_to: '2026.09.27',
  plan_loaded_at: '2026-09-19T08:00:00',
  looms: [
    {loom: 'D1', cells: {
      '2026.09.21': {order_no: '1557', product: 'P1', size: '150', design: 'D144', gsm: 420, product_code: 'P1',
        pile_yarn: '20/2', fact: {towels: 300, eff: 88, norm: 95}},
    }},
    {loom: 'D2', cells: {'2026.09.21': {order_no: '2000', product: 'A'}}},
  ],
});
const catalog = (): CatalogOrder[] => [
  {order_no: '1557', in_1c: true, in_plan: true, qty: 5000, due_day: '2026-10-01', products: [
    {product_code: 'P1', size: '150', design: 'D144', gsm: 420, qty: 5000, done: 300, expected: 400}],
    cells: 1, done: 300, expected: 400, looms: ['D1']},
  {order_no: '2000', in_1c: true, in_plan: false, qty: 1000, products: [
    {product_code: 'A', qty: 400, done: 0, expected: 0}, {product_code: 'B', qty: 600, done: 0, expected: 0}],
    cells: 0, done: 0, expected: 0, looms: []},
];

function bridge(): PlanBridge {
  const f = legacyFormatters();
  return {can: () => true, say: vi.fn(), expire: vi.fn(), refreshPlan: vi.fn(), esc: f.esc, nf: f.nf, fday: f.fday, ftime: f.ftime, dmy: f.dmy};
}

function mount() {
  document.body.innerHTML = loomMarkup;
  const el = (sel: string) => document.querySelector(sel) as HTMLElement;
  const periodBar = el('#lp-from').closest('.bar') as HTMLElement;
  const editBar = el('#lp-span').closest('.bar') as HTMLElement;
  const noteEl = el('#lp-note'), contextEl = el('.lp-context'), table = el('#lp-table');
  const palette = el('.lp-pal'), orderList = el('#lp-order-list'), dialog = document.querySelector('#lp-dlg') as HTMLDialogElement;
  const wrapEl = el('.lp-wrap'), scrollEl = el('#lp-scroll');
  [periodBar, editBar, contextEl, table, palette, orderList, dialog].forEach(x => x.replaceChildren());
  const rerenderBox = {current: () => {}};
  const io = {
    requestGrid: vi.fn<(f: string, t: string, s: AbortSignal) => Promise<LoomGrid>>().mockResolvedValue(grid()),
    requestCatalog: vi.fn<(s: AbortSignal) => Promise<Catalog>>().mockResolvedValue({orders: catalog()}),
    postCells: vi.fn<(c: CellChange[]) => Promise<{ok: number; picked?: {ambiguous?: number}; report_days: string[]}>>()
      .mockResolvedValue({ok: 1, report_days: []}),
    uploadExcel: vi.fn(), changed: () => rerenderBox.current(), say: vi.fn(), canEdit: () => true,
    dmy: (d: string) => d.slice(8, 10) + '.' + d.slice(5, 7), refreshPlan: vi.fn(),
  };
  const controller = new LoomController('2026.09.21', '2026.09.22', io);
  const b = bridge();
  function Harness() {
    const [, force] = useState(0);
    rerenderBox.current = () => force(n => n + 1);
    return <Loom periodBar={periodBar} editBar={editBar} noteEl={noteEl} contextEl={contextEl} table={table}
      palette={palette} orderList={orderList} dialog={dialog} wrapEl={wrapEl} scrollEl={scrollEl}
      state={controller.state} bridge={b} controller={controller}/>;
  }
  render(<Harness/>);
  void controller.load();
  return {controller, io, periodBar, editBar, noteEl, contextEl, table, palette, orderList, dialog, wrapEl, scrollEl, bridge: b};
}

const dataTransfer = () => {
  const store: Record<string, string> = {};
  return {setData: (t: string, v: string) => { store[t] = v; }, getData: (t: string) => store[t] || '', effectAllowed: ''};
};

beforeEach(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {configurable: true, value(this: HTMLDialogElement) {this.open = true;}},
    close: {configurable: true, value(this: HTMLDialogElement) {if (this.open) {this.open = false; this.dispatchEvent(new Event('close'));}}},
  });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {cleanup(); document.body.innerHTML = ''; vi.restoreAllMocks();});

describe('Parity with the original grid, orders list and order card', () => {
  it('renders the grid, thead, note and selection status exactly like the legacy renderer', async () => {
    const {controller, table} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    expect(loomGridOutput(document)).toEqual(loomGridOutput(legacyLoomGrid(grid(), catalog(), controller.state.today)));
    void table;
  });
  it('reflects a selected, focused cell exactly like the legacy renderer', async () => {
    const {controller} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    act(() => controller.click(key('D1', '2026.09.21'), {shift: false, ctrl: false}));
    await vi.waitFor(() => expect(controller.state.focus).toBe('1557'));
    expect(loomGridOutput(document)).toEqual(loomGridOutput(
      legacyLoomGrid(grid(), catalog(), controller.state.today, [key('D1', '2026.09.21')], '1557')));
  });
  it('renders the order palette exactly like the legacy renderer, including an expanded multi-product order', async () => {
    const {controller} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    expect(ordersListOutput(document)).toEqual(ordersListOutput(legacyOrdersList(catalog(), '', 'all', null, [])));
  });
  it('renders the focused order card exactly like the legacy renderer', async () => {
    const {controller} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    act(() => controller.clickOrderCard('1557', false));
    await vi.waitFor(() => expect(controller.state.focus).toBe('1557'));
    expect(orderCardOutput(document)).toEqual(orderCardOutput(legacyOrderCard(catalog(), '1557')));
  });
  it('hides the card when nothing is focused, like the legacy markup', async () => {
    const {controller} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    expect(document.querySelector('#lp-card')?.classList.contains('hidden')).toBe(true);
  });
});

describe('Selection and dialog interactions', () => {
  it('selects a cell on click and shows an editable single-cell status', async () => {
    const {controller, table} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    fireEvent.click(table.querySelector('td.d[data-k="D1|2026.09.21"]')!);
    expect(controller.state.selection.has(key('D1', '2026.09.21'))).toBe(true);
  });
  it('opens the edit dialog on double-click and saves the typed order', async () => {
    const {controller, table, dialog, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    fireEvent.doubleClick(table.querySelector('td.d[data-k="D2|2026.09.22"]')!);
    await vi.waitFor(() => expect(dialog.open).toBe(true));
    fireEvent.change(dialog.querySelector('#lp-d-order')!, {target: {value: '1557'}});
    dialog.returnValue = 'save'; dialog.close();
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    // Single-product orders are matched server-side (rematch()); the dialog itself doesn't auto-fill product_code.
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D2', day: '2026.09.22', order_no: '1557', product_code: null, note: null}]);
  });
  it('cancels the dialog without saving on Escape-equivalent close', async () => {
    const {controller, table, dialog, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    fireEvent.doubleClick(table.querySelector('td.d[data-k="D2|2026.09.22"]')!);
    await vi.waitFor(() => expect(dialog.open).toBe(true));
    dialog.returnValue = ''; dialog.close();
    expect(io.postCells).not.toHaveBeenCalled();
    expect(controller.state.dialog).toBeNull();
  });
});

describe('Drag and drop', () => {
  it('drops an order from the palette onto an empty cell', async () => {
    const {controller, table, palette, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    const dt = dataTransfer();
    fireEvent.dragStart(palette.querySelector('.oc[data-o="1557"]')!, {dataTransfer: dt});
    const target = table.querySelector('td.d[data-k="D2|2026.09.22"]')!;
    fireEvent.drop(target, {dataTransfer: dt});
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D2', day: '2026.09.22', order_no: '1557', product_code: 'P1', note: null}]);
  });
  it('moves a filled cell onto another, clearing the source', async () => {
    const {controller, table, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    const dt = dataTransfer();
    fireEvent.dragStart(table.querySelector('td.d[data-k="D1|2026.09.21"]')!, {dataTransfer: dt});
    fireEvent.drop(table.querySelector('td.d[data-k="D2|2026.09.22"]')!, {dataTransfer: dt});
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    const applied = io.postCells.mock.calls[0][0];
    expect(applied).toEqual(expect.arrayContaining([
      expect.objectContaining({loom: 'D2', day: '2026.09.22', order_no: '1557'}),
      {loom: 'D1', day: '2026.09.21', order_no: null, note: null},
    ]));
  });
});

describe('Keyboard shortcuts', () => {
  it('deletes the selection with Delete', async () => {
    const {controller, table, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    fireEvent.click(table.querySelector('td.d[data-k="D2|2026.09.21"]')!);
    fireEvent.keyDown(document, {key: 'Delete'});
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    expect(io.postCells).toHaveBeenCalledWith([{loom: 'D2', day: '2026.09.21', order_no: null, note: null}]);
  });
  it('clears the selection on Escape', async () => {
    const {controller, table} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    fireEvent.click(table.querySelector('td.d[data-k="D1|2026.09.21"]')!);
    fireEvent.keyDown(document, {key: 'Escape'});
    expect(controller.state.selection.size).toBe(0);
  });
  it('ignores shortcuts while typing in a form field', async () => {
    const {controller, table, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    fireEvent.click(table.querySelector('td.d[data-k="D2|2026.09.21"]')!);
    const input = document.createElement('input'); document.body.appendChild(input); input.focus();
    fireEvent.keyDown(input, {key: 'Delete'});
    expect(io.postCells).not.toHaveBeenCalled();
    input.remove();
  });
});

describe('Toolbar', () => {
  it('undo is disabled with an empty stack and enabled after a change', async () => {
    const {controller, editBar, table, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    expect(editBar.querySelector<HTMLButtonElement>('#lp-undo')!.disabled).toBe(true);
    fireEvent.click(table.querySelector('td.d[data-k="D2|2026.09.21"]')!);
    fireEvent.keyDown(document, {key: 'Delete'});
    await vi.waitFor(() => expect(io.postCells).toHaveBeenCalled());
    await vi.waitFor(() => expect(editBar.querySelector<HTMLButtonElement>('#lp-undo')!.disabled).toBe(false));
  });
  it('uploads the chosen Excel file', async () => {
    const {controller, editBar, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    io.uploadExcel.mockResolvedValueOnce({from: '2026-09-21', to: '2026-09-27', looms: 2, orders: [], notes: []});
    const input = editBar.querySelector<HTMLInputElement>('input[type=file]')!;
    const file = new File(['x'], 'plan.xlsx');
    Object.defineProperty(input, 'files', {value: [file]});
    fireEvent.change(input);
    await vi.waitFor(() => expect(io.uploadExcel).toHaveBeenCalledWith(file));
  });
  it('moves the period a week forward and reloads', async () => {
    const {controller, periodBar, io} = mount();
    await vi.waitFor(() => expect(controller.state.loaded).toBe(true));
    const buttons = periodBar.querySelectorAll('.lp-actions button');
    fireEvent.click(buttons[2]); // 7 дней →
    await vi.waitFor(() => expect(io.requestGrid).toHaveBeenCalledTimes(2));
  });
});
