import { requestJson } from '../report/http';
import type { Shift, WalkResponse } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestWalk(day: string, shift: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<WalkResponse>(`/api/walk?day=${day}&shift=${shift}`, expire, undefined, signal);
}

export type WalkState = {shifts: Shift[]; shiftIndex: number; loaded: boolean; data: WalkResponse | null};

export type WalkIO = {
  requestWalk: (day: string, shift: string, signal: AbortSignal) => Promise<WalkResponse>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: WalkState = {shifts: [], shiftIndex: -1, loaded: false, data: null};

export class WalkController {
  state: WalkState = initialState;
  private abort: AbortController | null = null;
  private seq = 0;
  private io: WalkIO;
  constructor(io: WalkIO) { this.io = io; }

  private set(next: Partial<WalkState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); }

  setShifts(shifts: Shift[]) {
    // По умолчанию — последняя закончившаяся смена (индекс 1), а не текущая.
    const shiftIndex = this.state.shiftIndex >= 0 && this.state.shiftIndex < shifts.length
      ? this.state.shiftIndex : (shifts.length > 1 ? 1 : shifts.length ? 0 : -1);
    this.set({shifts, shiftIndex});
  }

  setShiftIndex(shiftIndex: number) { this.set({shiftIndex}); }

  async load() {
    const s = this.state.shifts[this.state.shiftIndex];
    if (!s) return;
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const data = await this.io.requestWalk(s.day, s.shift, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      this.set({loaded: true, data});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Обход не загрузился: ' + message(e), true);
    }
  }
}
