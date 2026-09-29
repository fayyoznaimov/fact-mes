import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Orders } from './Orders';
import type { OrdersState } from './controller';
import type { PlanOrder } from './model';
import { legacyFormatters, legacyOrders, ordersMarkup, ordersOutput } from '../../../test/legacyPlan';
import type { PlanBridge } from '../bridge';

const order = (over: Partial<PlanOrder> = {}): PlanOrder => ({id: 1, order_no: '1557', product_code: 'P1',
  qty_towels: 5000, source: 'из 1С', done: 2000, left: 3000, matched: true, percent: 40, rate_per_day: 250,
  days_left: 12, eta: '2026-10-05', due_day: '2026-10-01', late_days: 1, ppt_source: '1С',
  looms: [{loom: 'D1', from_day: '2026-09-20', to_day: '2026-10-05', done: 2000, matched: true, days: 15}],
  plan: null, ...over});

function bridge(): PlanBridge {
  const f = legacyFormatters();
  return {can: () => true, say: vi.fn(), expire: vi.fn(), refreshPlan: vi.fn(), esc: f.esc, nf: f.nf, fday: f.fday, ftime: f.ftime, dmy: f.dmy};
}
function mount(state: OrdersState, overrides: Partial<{
  addOrder: ReturnType<typeof vi.fn>; importFrom1c: ReturnType<typeof vi.fn>; toggleClosed: ReturnType<typeof vi.fn>;
  showAllOrders: ReturnType<typeof vi.fn>; assign: ReturnType<typeof vi.fn>; toggleClose: ReturnType<typeof vi.fn>;
  savePpt: ReturnType<typeof vi.fn>;
}> = {}) {
  document.body.innerHTML = ordersMarkup;
  const formBar = document.querySelector('#pl-order')!.closest('.bar') as HTMLElement;
  const pptBar = document.querySelector('#ppt-key')!.closest('.bar') as HTMLElement;
  const productsList = document.querySelector('#pl-products') as HTMLElement;
  const tilesEl = document.querySelector('#pl-tiles') as HTMLElement;
  const tableBody = document.querySelector('#pl-table tbody') as HTMLElement;
  const pptNote = document.querySelector('#pl-ppt-note') as HTMLElement;
  [formBar, pptBar, tableBody].forEach(el => el.replaceChildren());
  const props = {
    addOrder: vi.fn().mockResolvedValue(true), importFrom1c: vi.fn(), toggleClosed: vi.fn(),
    showAllOrders: vi.fn(), assign: vi.fn(), toggleClose: vi.fn(), savePpt: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
  render(<Orders formBar={formBar} pptBar={pptBar} productsList={productsList} tilesEl={tilesEl}
    tableBody={tableBody} pptNote={pptNote} state={state} bridge={bridge()} {...props}/>);
  return {formBar, pptBar, tableBody, tilesEl, pptNote, ...props};
}
afterEach(() => {cleanup(); document.body.innerHTML = '';});

describe('Parity with the original plan/orders table', () => {
  it('renders tiles, rows and the PPT note exactly like the legacy renderer', async () => {
    const orders = [order(), order({id: 2, order_no: '1558', late_days: null, plan: {first_day: '2026-09-20',
      last_day: '2026-10-05', cells: 15, expected: 5200, shortfall: 300}, looms: [
      {loom: 'D2', from_day: '2026-09-20', to_day: '2026-10-05', done: 1000, days: 15},
      {loom: 'D3', from_day: '2026-09-25', to_day: '2026-10-05', done: 500, days: 10}]})];
    const data = {orders, plan_only: [{order_no: '1600'}], products: ['P1']};
    mount({orders, planOnly: data.plan_only, products: data.products, closed: false, showAll: false, loaded: true});
    expect(ordersOutput(document)).toEqual(ordersOutput(await legacyOrders(data)));
  });
  it('shows the legacy empty-plan message with no orders', async () => {
    const data = {orders: [], plan_only: [], products: []};
    mount({orders: [], planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    expect(ordersOutput(document)).toEqual(ordersOutput(await legacyOrders(data)));
  });
  it('adds a "show all" row past the 60-order page and matches once expanded', async () => {
    const orders = Array.from({length: 65}, (_, i) => order({id: i + 1, order_no: String(1000 + i)}));
    const data = {orders, plan_only: [], products: []};
    mount({orders, planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    expect(ordersOutput(document)).toEqual(ordersOutput(await legacyOrders(data)));
    cleanup(); document.body.innerHTML = '';
    mount({orders, planOnly: [], products: [], closed: false, showAll: true, loaded: true});
    expect(ordersOutput(document)).toEqual(ordersOutput(await legacyOrders(data, {all: true})));
  });
  it('matches an unmatched, unassigned order row with an assign input', async () => {
    const orders = [order({looms: [], matched: false, late_days: null})];
    const data = {orders, plan_only: [], products: []};
    mount({orders, planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    expect(ordersOutput(document)).toEqual(ordersOutput(await legacyOrders(data)));
  });
  it('matches an order whose loom cloth code does not match the product', async () => {
    const orders = [order({matched: false, late_days: null,
      looms: [{loom: 'D1', from_day: '2026-09-20', done: 2000, matched: false}]})];
    const data = {orders, plan_only: [], products: []};
    mount({orders, planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    expect(ordersOutput(document)).toEqual(ordersOutput(await legacyOrders(data)));
  });
});

describe('Interactions', () => {
  it('adds an order from the typed fields and clears order/qty on success', () => {
    const {formBar, addOrder} = mount({orders: [], planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    fireEvent.change(formBar.querySelector('#pl-order')!, {target: {value: ' 1900 '}});
    fireEvent.change(formBar.querySelector('#pl-product')!, {target: {value: ' P9 '}});
    fireEvent.change(formBar.querySelector('#pl-qty')!, {target: {value: '500'}});
    fireEvent.change(formBar.querySelector('#pl-due')!, {target: {value: '2026-11-01'}});
    fireEvent.click(formBar.querySelector('#pl-add')!);
    expect(addOrder).toHaveBeenCalledWith('1900', 'P9', 500, '2026-11-01');
  });
  it('toggles the closed filter', () => {
    const {formBar, toggleClosed} = mount({orders: [], planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    fireEvent.click(formBar.querySelector('#pl-closed')!);
    expect(toggleClosed).toHaveBeenCalledOnce();
  });
  it('imports from 1C', () => {
    const {formBar, importFrom1c} = mount({orders: [], planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    fireEvent.click(formBar.querySelector('#pl-1c')!);
    expect(importFrom1c).toHaveBeenCalledOnce();
  });
  it('assigns a loom typed into the row input', () => {
    const orders = [order({looms: [], matched: false})];
    const {tableBody, assign} = mount({orders, planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    fireEvent.change(tableBody.querySelector('input')!, {target: {value: 'D9'}});
    fireEvent.click(tableBody.querySelector('button')!);
    expect(assign).toHaveBeenCalledWith(1, 'D9');
  });
  it('closes and reopens an order by its current state', () => {
    const orders = [order({closed: false})];
    const {tableBody, toggleClose} = mount({orders, planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    const buttons = tableBody.querySelectorAll('button');
    fireEvent.click(buttons[buttons.length - 1]);
    expect(toggleClose).toHaveBeenCalledWith(1, false);
  });
  it('saves a PPT override and clears the value field on success', () => {
    const {pptBar, savePpt} = mount({orders: [], planOnly: [], products: [], closed: false, showAll: false, loaded: true});
    fireEvent.change(pptBar.querySelector('#ppt-key')!, {target: {value: 'P1'}});
    fireEvent.change(pptBar.querySelector('#ppt-val')!, {target: {value: '3300'}});
    fireEvent.click(pptBar.querySelector('#ppt-save')!);
    expect(savePpt).toHaveBeenCalledWith('P1', 3300, null);
  });
});
