import { afterEach, describe, expect, it, vi } from 'vitest';
import { OrdersController } from './controller';
import type { PlanData, PlanOrder } from './model';

const order = (over: Partial<PlanOrder> = {}): PlanOrder => ({id: 1, order_no: '1557', product_code: 'P1',
  qty_towels: 100, done: 40, left: 60, matched: true, percent: 40, rate_per_day: 10, days_left: 6,
  eta: '2026-09-30', due_day: '2026-10-01', late_days: -1, looms: [], plan: null, ...over});
const plan = (orders: PlanOrder[] = [order()]): PlanData => ({orders, plan_only: [], products: ['P1']});
function setup() {
  const io = {
    request: vi.fn<(closed: boolean, signal: AbortSignal) => Promise<PlanData>>(),
    changed: vi.fn(), onData: vi.fn(), say: vi.fn(),
    postOrder: vi.fn<(o: string, p: string, q: number, d: string) => Promise<void>>(),
    postImport1c: vi.fn<() => Promise<{error?: string; orders?: number; looms?: number}>>(),
    postAssign: vi.fn<(id: number, loom: string) => Promise<void>>(),
    postClose: vi.fn<(id: number, closed: boolean) => Promise<void>>(),
    postPpt: vi.fn<(k: string, p: number, pn: number | null) => Promise<void>>(),
  };
  const controller = new OrdersController(io);
  return {controller, io};
}
afterEach(() => vi.restoreAllMocks());

describe('Loading the plan', () => {
  it('loads orders and pushes the raw payload to the cloth-map subscriber', async () => {
    const {controller: c, io} = setup(), data = plan();
    io.request.mockResolvedValueOnce(data);
    await c.load();
    expect(c.state.orders).toEqual(data.orders);
    expect(c.state.loaded).toBe(true);
    expect(io.onData).toHaveBeenCalledWith(data);
  });
  it('reports a failed load without touching a previous snapshot', async () => {
    const {controller: c, io} = setup();
    io.request.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('План не загрузился: нет сети', true);
    expect(c.state.loaded).toBe(false);
  });
  it('toggling closed re-fetches with the closed flag and resets pagination', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValue(plan());
    c.state = {...c.state, showAll: true};
    c.toggleClosed();
    await Promise.resolve(); await Promise.resolve();
    expect(io.request).toHaveBeenCalledWith(true, expect.anything());
    expect(c.state.showAll).toBe(false);
  });
  it('showAllOrders flips the pagination flag without a fetch', () => {
    const {controller: c, io} = setup();
    c.showAllOrders();
    expect(c.state.showAll).toBe(true);
    expect(io.request).not.toHaveBeenCalled();
  });
});

describe('Adding an order', () => {
  it('rejects an incomplete form without calling the API', async () => {
    const {controller: c, io} = setup();
    expect(await c.addOrder('', 'P1', 10, '')).toBe(false);
    expect(io.postOrder).not.toHaveBeenCalled();
    expect(io.say).toHaveBeenCalledWith('Нужны заказ, изделие и количество', true);
  });
  it('adds, reports success and reloads', async () => {
    const {controller: c, io} = setup();
    io.postOrder.mockResolvedValueOnce(undefined); io.request.mockResolvedValueOnce(plan());
    expect(await c.addOrder('1557', 'P1', 100, '2026.10.01')).toBe(true);
    expect(io.postOrder).toHaveBeenCalledWith('1557', 'P1', 100, '2026.10.01');
    expect(io.say).toHaveBeenCalledWith('Заказ поставлен в план');
  });
  it('reports a failed add without reloading', async () => {
    const {controller: c, io} = setup();
    io.postOrder.mockRejectedValueOnce(new Error('дубликат'));
    expect(await c.addOrder('1557', 'P1', 100, '')).toBe(false);
    expect(io.say).toHaveBeenCalledWith('Не добавился: дубликат', true);
    expect(io.request).not.toHaveBeenCalled();
  });
});

describe('1C import', () => {
  it('reports the imported counts and reloads', async () => {
    const {controller: c, io} = setup();
    io.postImport1c.mockResolvedValueOnce({orders: 5, looms: 3}); io.request.mockResolvedValueOnce(plan());
    await c.importFrom1c();
    expect(io.say).toHaveBeenCalledWith('Из 1С взято заказов 5, станков 3', false);
  });
  it('surfaces a server-reported error as an error toast', async () => {
    const {controller: c, io} = setup();
    io.postImport1c.mockResolvedValueOnce({error: 'ключ 1С истёк'});
    await c.importFrom1c();
    expect(io.say).toHaveBeenCalledWith('ключ 1С истёк', true);
  });
});

describe('Assign, close and PPT', () => {
  it('rejects an empty loom without calling the API', async () => {
    const {controller: c, io} = setup();
    await c.assign(1, '   ');
    expect(io.postAssign).not.toHaveBeenCalled();
    expect(io.say).toHaveBeenCalledWith('Укажите станок', true);
  });
  it('trims the loom and assigns', async () => {
    const {controller: c, io} = setup();
    io.postAssign.mockResolvedValueOnce(undefined); io.request.mockResolvedValueOnce(plan());
    await c.assign(1, ' D1 ');
    expect(io.postAssign).toHaveBeenCalledWith(1, 'D1');
  });
  it('toggles closed state to its opposite', async () => {
    const {controller: c, io} = setup();
    io.postClose.mockResolvedValueOnce(undefined); io.request.mockResolvedValueOnce(plan());
    await c.toggleClose(1, false);
    expect(io.postClose).toHaveBeenCalledWith(1, true);
  });
  it('rejects an empty PPT form without calling the API', async () => {
    const {controller: c, io} = setup();
    expect(await c.savePpt('', 0, null)).toBe(false);
    expect(io.postPpt).not.toHaveBeenCalled();
  });
  it('saves PPT, reports success and reloads', async () => {
    const {controller: c, io} = setup();
    io.postPpt.mockResolvedValueOnce(undefined); io.request.mockResolvedValueOnce(plan());
    expect(await c.savePpt('P1', 3300, 4)).toBe(true);
    expect(io.postPpt).toHaveBeenCalledWith('P1', 3300, 4);
    expect(io.say).toHaveBeenCalledWith('Сохранено: P1 — 3300 пиков');
  });
});
