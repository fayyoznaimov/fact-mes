import { requestJson } from '../report/http';
import type { Category, Filter, LiveResponse, Sort, Ticket, TicketsResponse } from './model';
import { dash2dot, nextSort as nextSortOf, todayForShift } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestTickets(from: string, to: string, openOnly: boolean, expire: () => void, signal?: AbortSignal) {
  const q = `from=${from}&to=${to}` + (openOnly ? '&open=1' : '');
  return requestJson<TicketsResponse>(`/api/tickets?limit=5000&${q}`, expire, undefined, signal);
}
export function requestLive(expire: () => void, signal?: AbortSignal) {
  return requestJson<LiveResponse>('/api/live', expire, undefined, signal);
}
export function postTicketNew(loom: string, expire: () => void) {
  return requestJson<{ok: true}>('/api/tickets/new', expire, {loom});
}
export function postTicketClose(id: number, expire: () => void) {
  return requestJson<{ok: true}>('/api/tickets/close', expire, {id});
}
export function postTicketClassify(id: number, categoryId: string, was: string | null, expire: () => void) {
  return requestJson<{ok: true}>('/api/tickets/classify', expire, {id, category_id: categoryId, was});
}

export type TicketsState = {
  from: string; to: string; shift: string; looms: string; filter: Filter;
  sort: Sort; show: number; loaded: boolean;
  tickets: Ticket[]; categories: Category[]; canEdit: boolean; live: LiveResponse | null;
  pick: Ticket | null;
};

export type TicketsIO = {
  requestTickets: (from: string, to: string, openOnly: boolean, signal: AbortSignal) => Promise<TicketsResponse>;
  requestLive: (signal: AbortSignal) => Promise<LiveResponse>;
  postNew: (loom: string) => Promise<unknown>;
  postClose: (id: number) => Promise<unknown>;
  postClassify: (id: number, categoryId: string, was: string | null) => Promise<unknown>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: TicketsState = {
  from: '', to: '', shift: '', looms: '', filter: 'all', sort: {k: 'started_at', dir: -1}, show: 100,
  loaded: false, tickets: [], categories: [], canEdit: false, live: null, pick: null,
};

export class TicketsController {
  state: TicketsState = initialState;
  private abort: AbortController | null = null;
  private io: TicketsIO;
  private now: () => Date;
  constructor(io: TicketsIO, now: () => Date = () => new Date()) { this.io = io; this.now = now; }

  private set(next: Partial<TicketsState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); }

  setFrom(from: string) { this.set({from}); void this.load(); }
  setTo(to: string) { this.set({to}); void this.load(); }
  setShift(shift: string) { this.set({shift, show: 100}); }
  setLooms(looms: string) { this.set({looms, show: 100}); }
  setFilter(filter: Filter) { this.set({filter}); void this.load(); }
  toggleSort(k: Sort['k']) { this.set({sort: nextSortOf(this.state.sort, k), show: 100}); }
  showMore() { this.set({show: this.state.show + 100}); }

  async load() {
    let {from, to} = this.state;
    if (!from) from = todayForShift(this.now());
    if (!to) to = from;
    this.set({from, to});
    const ac = new AbortController();
    this.abort?.abort();
    this.abort = ac;
    try {
      const [t, live] = await Promise.all([
        this.io.requestTickets(dash2dot(from), dash2dot(to), this.state.filter === 'open', ac.signal),
        this.io.requestLive(ac.signal),
      ]);
      if (ac.signal.aborted) return;
      this.set({loaded: true, tickets: t.tickets, categories: t.categories, canEdit: t.can_edit, live});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Тикеты не загрузились: ' + message(e), true);
    }
  }

  async newTicket(loom: string) {
    if (!this.state.canEdit) { this.io.say('Нет прав заводить тикеты', true); return; }
    try {
      await this.io.postNew(loom);
      await this.load();
    } catch (e) { this.io.say('Тикет не завёлся: ' + message(e), true); }
  }

  async closeTicket(id: number) {
    try {
      await this.io.postClose(id);
      await this.load();
    } catch (e) { this.io.say('Не закрылся: ' + message(e), true); }
  }

  openCategoryDialog(ticket: Ticket) { this.set({pick: ticket}); }
  closeCategoryDialog() { this.set({pick: null}); }

  async pickCategory(categoryId: string) {
    const ticket = this.state.pick;
    if (!ticket) return;
    try {
      await this.io.postClassify(ticket.id, categoryId, ticket.category_id);
      this.set({pick: null});
      this.io.say(`${ticket.loom}: причина записана`);
      await this.load();
    } catch (e) {
      this.set({pick: null});
      this.io.say('Не записалось: ' + message(e), true);
    }
  }
}
