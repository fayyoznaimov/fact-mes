import { requestJson } from '../report/http';
import type { ExplorerResponse, Group } from './model';
import { defaultRange, orderRange, shiftsParam, toggleShift } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestExplorer(from: string, to: string, shifts: string, group: Group, expire: () => void, signal?: AbortSignal) {
  return requestJson<ExplorerResponse>(`/api/explorer?from=${from}&to=${to}&shifts=${shifts}&group=${group}`, expire, undefined, signal);
}

export type ExplorerState = {
  days: string[]; from: string; to: string; shifts: Set<string>; group: Group;
  loaded: boolean; data: ExplorerResponse | null;
};

export type ExplorerIO = {
  requestExplorer: (from: string, to: string, shifts: string, group: Group, signal: AbortSignal) => Promise<ExplorerResponse>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: ExplorerState = {
  days: [], from: '', to: '', shifts: new Set(['A', 'B', 'C']), group: 'all', loaded: false, data: null,
};

export class ExplorerController {
  state: ExplorerState = initialState;
  private abort: AbortController | null = null;
  private seq = 0;
  private io: ExplorerIO;
  constructor(io: ExplorerIO) { this.io = io; }

  private set(next: Partial<ExplorerState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); }

  setDays(days: string[]) {
    const {from, to} = defaultRange(days);
    this.set({days, from, to});
  }

  setFrom(from: string) { this.set({from}); }
  setTo(to: string) { this.set({to}); }
  setGroup(group: Group) { this.set({group}); }
  toggleShift(letter: string) { this.set({shifts: toggleShift(this.state.shifts, letter)}); }

  async load() {
    const [from, to] = orderRange(this.state.from, this.state.to);
    const shifts = shiftsParam(this.state.shifts);
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const data = await this.io.requestExplorer(from, to, shifts, this.state.group, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      this.set({loaded: true, data});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Простои не загрузились: ' + message(e), true);
    }
  }
}
