import { requestJson } from '../report/http';
import type { SalaryResponse, Shift } from './model';

export function requestSalary(day: string, shift: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<SalaryResponse>(`/api/salary?day=${day}&shift=${shift}`, expire, undefined, signal);
}
export function postAssignOne(day: string, shift: string, loom: string, operatorId: number | null, expire: () => void) {
  return requestJson<{ok: true}>('/api/assign_one', expire, {day, shift, loom, operator_id: operatorId});
}
export function postAssignCopy(day: string, shift: string, expire: () => void) {
  return requestJson<{copied: number; from: string | null}>('/api/assign_copy', expire, {day, shift});
}

export type SalaryState = {
  shifts: Shift[]; shiftIndex: number; loaded: boolean; data: SalaryResponse | null;
};

export type SalaryIO = {
  requestSalary: (day: string, shift: string, signal: AbortSignal) => Promise<SalaryResponse>;
  postAssignOne: (day: string, shift: string, loom: string, operatorId: number | null) => Promise<unknown>;
  postAssignCopy: (day: string, shift: string) => Promise<{copied: number; from: string | null}>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: SalaryState = {shifts: [], shiftIndex: -1, loaded: false, data: null};

export class SalaryController {
  state: SalaryState = initialState;
  private abort: AbortController | null = null;
  private io: SalaryIO;
  private seq = 0;
  constructor(io: SalaryIO) { this.io = io; }

  private set(next: Partial<SalaryState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); }

  setShifts(shifts: Shift[]) {
    const shiftIndex = this.state.shiftIndex >= 0 && this.state.shiftIndex < shifts.length
      ? this.state.shiftIndex : (shifts.length ? 0 : -1);
    this.set({shifts, shiftIndex});
  }

  setShiftIndex(shiftIndex: number) { this.set({shiftIndex}); }

  private current(): Shift | null { return this.state.shifts[this.state.shiftIndex] || null; }

  async load() {
    const s = this.current();
    if (!s) return;
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const data = await this.io.requestSalary(s.day, s.shift, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      this.set({loaded: true, data});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Зарплата не посчиталась: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  async copy() {
    const s = this.current();
    if (!s) return;
    try {
      const r = await this.io.postAssignCopy(s.day, s.shift);
      this.io.say(r.copied ? `Перенесено со смены ${r.from}: станков ${r.copied}`
        : 'Не нашлось смены с расстановкой — назначьте вручную');
      await this.load();
    } catch (e) {
      this.io.say('Не перенеслось: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  async assign(loom: string, operatorId: number | null) {
    const s = this.current();
    if (!s) return;
    try {
      await this.io.postAssignOne(s.day, s.shift, loom, operatorId);
      this.io.say(operatorId ? `${loom}: оператор назначен` : `${loom}: снят`);
      await this.load();
    } catch (e) {
      this.io.say('Не сохранилось: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }
}
