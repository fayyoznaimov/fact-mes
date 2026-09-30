import { requestJson } from '../report/http';
import type { Group, ManualResponse } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestManual(from: string, to: string, group: Group, expire: () => void, signal?: AbortSignal) {
  return requestJson<ManualResponse>(`/api/manual_stops?from=${from}&to=${to}&group=${group}`, expire, undefined, signal);
}

export type ManualState = {days: string[]; from: string; to: string; group: Group; loaded: boolean; data: ManualResponse | null};

export type ManualIO = {
  requestManual: (from: string, to: string, group: Group, signal: AbortSignal) => Promise<ManualResponse>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: ManualState = {days: [], from: '', to: '', group: 'day', loaded: false, data: null};

export class ManualController {
  state: ManualState = initialState;
  private abort: AbortController | null = null;
  private seq = 0;
  private io: ManualIO;
  constructor(io: ManualIO) { this.io = io; }

  private set(next: Partial<ManualState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); }

  setDays(days: string[]) {
    if (!days.length) { this.set({days, from: '', to: ''}); return; }
    this.set({days, from: days[Math.min(days.length - 1, 29)] ?? days[days.length - 1], to: days[0]});
  }

  setFrom(from: string) { this.set({from}); }
  setTo(to: string) { this.set({to}); }
  setGroup(group: Group) { this.set({group}); void this.load(); }

  async load() {
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const data = await this.io.requestManual(this.state.from, this.state.to, this.state.group, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      this.set({loaded: true, data});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Сводка ручных остановов не загрузилась: ' + message(e), true);
    }
  }
}
