import { requestJson } from '../report/http';
import type { MachineHistory, Period, SignalsResponse } from './model';
import { flattenSignalValues, loomsParam } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestHistory(day: string, period: Period, looms: string, expire: () => void, signal?: AbortSignal) {
  const q = new URLSearchParams({day, period, looms});
  return requestJson<MachineHistory>(`/api/machine_history?${q}`, expire, undefined, signal);
}
export function requestSignals(loom: string, day: string, period: string, expire: () => void, signal?: AbortSignal) {
  const q = new URLSearchParams({loom, day, period});
  return requestJson<SignalsResponse>(`/api/machine_signals?${q}`, expire, undefined, signal);
}

export type Detail = {kind: 'event' | 'ticket'; index: number};
export type SignalsState = {loading: boolean; error: string | null; data: SignalsResponse | null; selectedKey: string | null};
export type HistoryState = {
  day: string; period: Period; loomSelect: string; zoom: 1 | 2 | 4;
  loading: boolean; loaded: boolean; data: MachineHistory | null; catalog: string[]; error: string | null;
  selectedRow: number | null; page: number; detail: Detail | null;
  signals: SignalsState;
};

export type HistoryIO = {
  requestHistory: (day: string, period: Period, looms: string, signal: AbortSignal) => Promise<MachineHistory>;
  requestSignals: (loom: string, day: string, period: string, signal: AbortSignal) => Promise<SignalsResponse>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialSignals: SignalsState = {loading: false, error: null, data: null, selectedKey: null};
const initialState: HistoryState = {
  day: '', period: 'day', loomSelect: '', zoom: 1, loading: false, loaded: false, data: null, catalog: [],
  error: null, selectedRow: null, page: 0, detail: null, signals: initialSignals,
};

export class HistoryController {
  state: HistoryState = initialState;
  private abort: AbortController | null = null;
  private signalsAbort: AbortController | null = null;
  private seq = 0;
  private io: HistoryIO;
  constructor(io: HistoryIO) { this.io = io; }

  private set(next: Partial<HistoryState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); this.signalsAbort?.abort(); }

  // Уходя со вкладки, отдаём ~40 тыс. элементов SVG: висящие скрытыми, они всё
  // равно занимают память, а вкладку открывают заново при каждом возврате.
  clear() { this.set({data: null, loaded: false, selectedRow: null, page: 0, detail: null, signals: initialSignals}); }

  setDay(day: string) { this.set({day}); }
  setPeriod(period: Period) { this.set({period}); }
  setZoom(zoom: 1 | 2 | 4) { this.set({zoom}); }
  setLoomSelect(loomSelect: string) { this.set({loomSelect}); void this.load(); }

  async load() {
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    const looms = loomsParam(this.state.loomSelect, this.state.catalog);
    this.set({loading: true, error: null, selectedRow: null, page: 0, detail: null, signals: initialSignals});
    try {
      const data = await this.io.requestHistory(this.state.day, this.state.period, looms, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      this.set({loading: false, loaded: true, data, catalog: data.catalog, day: data.day});
      if (data.rows.length === 1) this.selectRow(0);
    } catch (e) {
      if (ac.signal.aborted) return;
      this.set({loading: false, data: null, error: 'История не загрузилась: ' + message(e)});
    }
  }

  selectRow(index: number) {
    this.set({selectedRow: index, page: 0, detail: null, signals: initialSignals});
    void this.loadSignals();
  }

  setPage(page: number) { this.set({page}); }
  showEventDetail(index: number) { this.set({detail: {kind: 'event', index}}); }
  showTicketDetail(index: number) { this.set({detail: {kind: 'ticket', index}}); }

  private async loadSignals() {
    const row = this.currentRow();
    const mh = this.state.data;
    if (!row || !mh) return;
    this.signalsAbort?.abort();
    const ac = new AbortController();
    this.signalsAbort = ac;
    this.set({signals: {...initialSignals, loading: true}});
    try {
      const data = await this.io.requestSignals(row.loom, mh.day, mh.period, ac.signal);
      if (ac.signal.aborted) return;
      const keys = [...new Set(data.samples.flatMap(s => Object.keys(flattenSignalValues(s.values))))].sort();
      this.set({signals: {loading: false, error: null, data, selectedKey: keys.includes('state') ? 'state' : keys[0] || null}});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.set({signals: {loading: false, error: message(e), data: null, selectedKey: null}});
    }
  }

  setSignalKey(key: string) { this.set({signals: {...this.state.signals, selectedKey: key}}); }

  currentRow() {
    const {data, selectedRow} = this.state;
    return selectedRow != null ? data?.rows[selectedRow] ?? null : null;
  }
}
