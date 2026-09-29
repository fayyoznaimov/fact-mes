import { requestJson } from '../../report/http';
import type { PlanData, PlanOrder } from './model';

export type OrdersState = {orders: PlanOrder[]; planOnly: {order_no: string}[]; products: string[];
  closed: boolean; showAll: boolean; loaded: boolean};
export type OrdersIO = {
  request: (closed: boolean, signal: AbortSignal) => Promise<PlanData>;
  changed: () => void;
  onData: (data: PlanData) => void; // тот же ответ уходит подвкладке «Коды ткани» — второй запрос не нужен.
  say: (text: string, isErr?: boolean) => void;
  postOrder: (orderNo: string, productCode: string, qty: number, due: string) => Promise<void>;
  postImport1c: () => Promise<{error?: string; orders?: number; looms?: number}>;
  postAssign: (orderId: number, loom: string) => Promise<void>;
  postClose: (orderId: number, closed: boolean) => Promise<void>;
  postPpt: (key: string, ppt: number, panels: number | null) => Promise<void>;
};
const message = (e: unknown) => e instanceof Error ? e.message : String(e);

// Independent of React and DOM: one owner for the plan snapshot and its write actions.
export class OrdersController {
  state: OrdersState = {orders: [], planOnly: [], products: [], closed: false, showAll: false, loaded: false};
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;

  constructor(private io: OrdersIO) {}

  toggleClosed() {
    this.state = {...this.state, closed: !this.state.closed, showAll: false};
    void this.load();
  }
  showAllOrders() { this.state = {...this.state, showAll: true}; this.io.changed(); }

  async load() {
    this.pending?.abort();
    if (this.disposed) return;
    const id = ++this.requestId, abort = new AbortController();
    this.pending = abort;
    try {
      const data = await this.io.request(this.state.closed, abort.signal);
      if (id !== this.requestId || this.disposed) return;
      this.state = {...this.state, orders: data.orders, planOnly: data.plan_only || [], products: data.products || [], loaded: true};
      this.io.changed();
      this.io.onData(data);
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      this.io.say('План не загрузился: ' + message(error), true);
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  async addOrder(orderNo: string, productCode: string, qty: number, due: string) {
    if (!orderNo || !productCode || !qty) {this.io.say('Нужны заказ, изделие и количество', true); return false;}
    try {
      await this.io.postOrder(orderNo, productCode, qty, due);
      this.io.say('Заказ поставлен в план');
      void this.load();
      return true;
    } catch (e) { this.io.say('Не добавился: ' + message(e), true); return false; }
  }

  async importFrom1c() {
    try {
      const r = await this.io.postImport1c();
      this.io.say(r.error ? r.error : `Из 1С взято заказов ${r.orders}, станков ${r.looms}`, !!r.error);
      void this.load();
    } catch (e) { this.io.say('Не получилось: ' + message(e), true); }
  }

  async assign(orderId: number, loom: string) {
    if (!loom.trim()) {this.io.say('Укажите станок', true); return;}
    try { await this.io.postAssign(orderId, loom.trim()); void this.load(); }
    catch (e) { this.io.say('Не поставилось: ' + message(e), true); }
  }

  async toggleClose(orderId: number, closed: boolean) {
    try { await this.io.postClose(orderId, !closed); void this.load(); }
    catch (e) { this.io.say('Не закрылось: ' + message(e), true); }
  }

  async savePpt(key: string, ppt: number, panels: number | null) {
    if (!key || !ppt) {this.io.say('Нужны артикул (или код ткани) и число пиков', true); return false;}
    try {
      await this.io.postPpt(key, ppt, panels);
      this.io.say(`Сохранено: ${key} — ${ppt} пиков`);
      void this.load();
      return true;
    } catch (e) { this.io.say('Не сохранилось: ' + message(e), true); return false; }
  }

  dispose() { this.disposed = true; this.pending?.abort(); }
}

export async function requestPlan(closed: boolean, signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<PlanData>('/api/plan' + (closed ? '?closed=1' : ''), expire, undefined, signal);
}
export async function requestAddOrder(orderNo: string, productCode: string, qty: number, due: string, expire: () => void) {
  await requestJson('/api/plan/order', expire, {order_no: orderNo, product_code: productCode, qty_towels: qty, due_day: due});
}
export async function requestImport1c(expire: () => void) {
  return requestJson<{error?: string; orders?: number; looms?: number}>('/api/plan/import_1c', expire, {});
}
export async function requestAssign(orderId: number, loom: string, expire: () => void) {
  await requestJson('/api/plan/assign', expire, {order_id: orderId, loom});
}
export async function requestClose(orderId: number, closed: boolean, expire: () => void) {
  await requestJson('/api/plan/close', expire, {order_id: orderId, closed});
}
export async function requestSavePpt(key: string, ppt: number, panels: number | null, expire: () => void) {
  await requestJson('/api/plan/ppt', expire, {key, ppt, panels});
}
