import { requestJson } from '../report/http';
import type { DashResponse, ForecastResponse, ShowOnly } from './model';

export function requestDashboard(day: string, shift: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<DashResponse>(`/api/dashboard?day=${day}&shift=${shift}`, expire, undefined, signal);
}
export function requestForecast(expire: () => void, signal?: AbortSignal) {
  return requestJson<ForecastResponse>('/api/forecast?hours=12', expire, undefined, signal);
}
export function postLoomArticle(loom: string, productCode: string, day: string, expire: () => void) {
  return requestJson<{ok: true}>('/api/loom_article', expire, {loom, product_code: productCode, day});
}

export type DashState = {
  days: string[]; day: string; shift: string; only: ShowOnly;
  loaded: boolean;
  data: DashResponse | null;
  forecast: ForecastResponse | null;
  open: Set<string>;
};

export type DashIO = {
  requestDashboard: (day: string, shift: string, signal: AbortSignal) => Promise<DashResponse>;
  requestForecast: (signal: AbortSignal) => Promise<ForecastResponse>;
  postLoomArticle: (loom: string, productCode: string, day: string) => Promise<unknown>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: DashState = {days: [], day: '', shift: '', only: 'all', loaded: false, data: null, forecast: null, open: new Set()};

export class DashController {
  state: DashState = initialState;
  private abort: AbortController | null = null;
  private forecastAbort: AbortController | null = null;
  private io: DashIO;
  private seq = 0;
  constructor(io: DashIO) { this.io = io; }

  private set(next: Partial<DashState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); this.forecastAbort?.abort(); }

  setDays(days: string[]) {
    const day = this.state.day && days.includes(this.state.day) ? this.state.day : (days[0] || '');
    this.set({days, day});
  }

  setDay(day: string) { this.set({day}); }
  setShift(shift: string) { this.set({shift}); }
  setOnly(only: ShowOnly) { this.set({only}); }

  cardsHref(): string {
    return `/cards?day=${this.state.day}` + (this.state.shift ? `&shift=${this.state.shift}` : '');
  }

  async load() {
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const data = await this.io.requestDashboard(this.state.day, this.state.shift, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      this.set({loaded: true, data});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Дашборд не загрузился: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  async loadSoon() {
    this.forecastAbort?.abort();
    const ac = new AbortController();
    this.forecastAbort = ac;
    try {
      const forecast = await this.io.requestForecast(ac.signal);
      if (ac.signal.aborted) return;
      this.set({forecast});
    } catch {
      if (ac.signal.aborted) return;
      this.set({forecast: null});
    }
  }

  toggleOpen(loom: string) {
    const open = new Set(this.state.open);
    if (open.has(loom)) open.delete(loom); else open.add(loom);
    this.set({open});
  }

  async setArticle(loom: string, productCode: string) {
    try {
      await this.io.postLoomArticle(loom, productCode, this.state.day);
      this.io.say(productCode ? `${loom}: заправлено ${productCode}` : `${loom}: артикул снят`);
      await this.load();
    } catch (e) {
      this.io.say('Не сохранилось: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }
}
