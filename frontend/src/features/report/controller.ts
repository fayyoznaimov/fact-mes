import { COLUMNS, paintRpm, type Row, type Snapshot, type View } from './model';
import { requestJson } from './http';

type Yarn = {slot: string; yarn?: string; lot?: string};
export type ReportIO = {
  request: (day: string, signal: AbortSignal) => Promise<unknown>;
  changed: () => void;
  publish: (rows: Row[]) => void;
  error: (message: string) => void;
  storage: Pick<Storage, 'getItem' | 'setItem'>;
};
const signature = COLUMNS.map(c => c.k).join(',');

export function prepareRows(data: unknown): Row[] {
  if (!data || typeof data !== 'object' || !('rows' in data) || !Array.isArray(data.rows))
    throw new Error('сервер вернул неверный формат отчёта');
  return data.rows.map(raw => {
    if (!raw || typeof raw !== 'object' || typeof raw.loom !== 'string')
      throw new Error('сервер вернул строку без номера станка');
    const row = {...raw} as Row;
    const marks = COLUMNS.filter(c => c.p && c.p !== paintRpm).map(c => c.p!(raw[c.k]));
    row._red = marks.some(m => m.includes('c-red'));
    row._yel = marks.some(m => m.includes('c-yel'));
    let yarns: Yarn[] = [];
    try {
      const parsed = typeof raw.yarns === 'string' ? JSON.parse(raw.yarns || '[]') : raw.yarns;
      if (Array.isArray(parsed)) yarns = parsed.filter(y => y && typeof y.slot === 'string');
    } catch { /* Повреждённая пряжа не скрывает остальные данные отчёта. */ }
    const by = Object.fromEntries(yarns.map(y => [y.slot, y]));
    Object.assign(row, {yarn_by: by});
    const show = (...slots: string[]) => slots.map(s => by[s]).filter(Boolean)
      .map(y => (y.yarn || '?') + (y.lot ? ' · ' + y.lot : '')).join(' + ');
    row.y_pile = show('pile'); row.y_ground = show('ground'); row.y_weft = show('weft1');
    row.y_hem = show('weft2', 'hemply', 'hempoly'); row.y_fancy = show('weft3', 'fancyply', 'weft4');
    return row;
  });
}

// Independent of React and DOM: one owner for requests, selected day and saved view.
export class ReportController {
  state: Snapshot;
  days: string[];
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;
  private displayedDay: string;

  constructor(initial: Snapshot, days: string[], private io: ReportIO) {
    this.state = initial;
    this.displayedDay = initial.day;
    this.days = days;
    try {
      const saved = JSON.parse(io.storage.getItem('rep-view') || '{}');
      const hidden = JSON.parse(io.storage.getItem('rep-hide') || '[]');
      const filters: Record<string, string> = {};
      if (saved.sig === signature && saved.f && typeof saved.f === 'object') {
        for (const [i, value] of Object.entries(saved.f))
          if (/^\d+$/.test(i) && COLUMNS[Number(i)] && typeof value === 'string') filters[i] = value;
        const sort = saved.sort;
        this.state = {...this.state, filters, sort: sort && Number.isInteger(sort.i) && COLUMNS[sort.i]
          && [1,-1].includes(sort.dir) ? {i:sort.i,dir:sort.dir} : null};
      }
      if (['all','red','warn'].includes(saved.flag)) this.state = {...this.state,flag:saved.flag};
      if (Array.isArray(hidden)) this.state = {...this.state,hidden:hidden.filter(g=>typeof g==='string')};
    } catch { /* Настройки браузера необязательны. */ }
  }

  setView(view: View) {
    this.state = {...this.state,filters:view.filters,sort:view.sort,hidden:view.hidden,flag:view.flag};
    try {
      this.io.storage.setItem('rep-view', JSON.stringify({f:view.filters,sort:view.sort,flag:view.flag,sig:signature}));
      this.io.storage.setItem('rep-hide', JSON.stringify(view.hidden));
    } catch { /* Отчёт работает и при недоступном localStorage. */ }
    this.io.changed();
  }

  setDays(days: string[]) {
    this.cancel();
    this.days = [...days];
    this.state = {...this.state,day:days[0] || '',rows:[],loading:false};
    this.displayedDay = this.state.day;
    this.io.publish([]);
    this.io.changed();
  }

  async load(autoSkip = false, day = this.state.day) {
    this.cancel();
    if (this.disposed || !day) return;
    const id = this.requestId, abort = new AbortController();
    this.pending = abort;
    this.state = {...this.state,day,loading:true};
    this.io.changed();
    try {
      for (;;) {
        const data = await this.io.request(day, abort.signal);
        // Request providers can finish even after abort; the generation check is required.
        if (id !== this.requestId || this.disposed) return;
        const rows = prepareRows(data);
        const index = this.days.indexOf(day);
        if (autoSkip && rows.length && rows.filter(r=>r.eff_c!=null).length < rows.length/2
            && index >= 0 && index < this.days.length-1) {
          day = this.days[index+1];
          continue;
        }
        this.state = {...this.state,rows,day,loading:false};
        this.displayedDay = day;
        this.io.publish(rows);
        this.io.changed();
        return;
      }
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      // Keep the last successful report paired with its date when a request fails.
      this.state = {...this.state,day:this.displayedDay,loading:false};
      this.io.changed();
      this.io.error('Отчёт не загрузился: ' + (error instanceof Error ? error.message : String(error)));
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  private cancel() { this.requestId++; this.pending?.abort(); this.pending = undefined; }
  dispose() { this.disposed = true; this.cancel(); }
}

export async function requestReport(day: string, signal: AbortSignal, expire: () => void): Promise<unknown> {
  return requestJson('/api/report?day='+encodeURIComponent(day),expire,undefined,signal);
}
