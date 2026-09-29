import { requestJson } from '../report/http';
import type { YarnRow } from './bridge';
import type { Column, SetupGridResponse, SetupGridRow } from './model';
import { anyBad, applyPaste, badYarnNames, dash2dot, fmtv, rowsDirty, sgColsFor, sgInFilter, shiftNow, yarnCanonicalize } from './model';

export function requestSetupGrid(day: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<SetupGridResponse>(`/api/setup_grid?day=${dash2dot(day)}`, expire, undefined, signal);
}
export function postYarn(body: unknown, expire: () => void) {
  return requestJson<{name: string; exists?: boolean; restored?: boolean}>('/api/yarns', expire, body);
}
export function postYarnUpdate(body: unknown, expire: () => void) {
  return requestJson<{ok: true; days: string[]}>('/api/yarns/update', expire, body);
}
export type YarnImportResult = {items: number; new: number; updated: number; yarns_added: string[]; no_kind: string[]};
export async function uploadYarnsFile(file: File, expire: () => void): Promise<YarnImportResult> {
  const response = await fetch('/api/yarns/import', {method: 'POST', credentials: 'same-origin', body: file});
  if (response.status === 401) { expire(); throw new Error('сессия закончилась — войдите снова'); }
  const data = await response.json();
  if (data?.error || !response.ok) throw new Error(data?.error || `сервер ответил ошибкой ${response.status}`);
  return data;
}

export type Posted = {id: number; number: string; after?: {days?: string[]; after_error?: string}};

export type SetupState = {
  day: string; time: string; filter: string;
  loaded: boolean;
  reportDay: string | null;
  rows: SetupGridRow[];
  cols: Column[];
  cells: Record<string, string>[];
  original: Record<string, string>[];
  focus: {r: number; c: number} | null;
  picked: Set<number>;
  saving: boolean;
};

export type SetupIO = {
  requestGrid: (day: string, signal: AbortSignal) => Promise<SetupGridResponse>;
  postYarn: (body: unknown) => Promise<{name: string; exists?: boolean; restored?: boolean}>;
  postYarnUpdate: (body: unknown) => Promise<unknown>;
  uploadYarns: (file: File) => Promise<YarnImportResult>;
  confirmSetup: (payload: unknown) => Promise<Posted | null>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
  yarns: () => YarnRow[];
  refreshYarns: () => Promise<void>;
  confirmDiscard: (text: string) => boolean;
};

const initialState: SetupState = {
  day: '', time: '07:00', filter: '', loaded: false, reportDay: null,
  rows: [], cols: [], cells: [], original: [], focus: null, picked: new Set(), saving: false,
};

export class SetupController {
  state: SetupState = initialState;
  private abort: AbortController | null = null;
  private io: SetupIO;
  constructor(io: SetupIO) { this.io = io; }

  private set(next: Partial<SetupState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); }

  isDirty(): boolean {
    return rowsDirty(this.state.cells, this.state.original, this.state.cols).length > 0;
  }

  async load(force = false) {
    if (!force && this.state.loaded && this.isDirty() && !this.io.confirmDiscard('Есть несохранённые правки — выбросить их?')) return;
    const day = this.state.day || shiftNow().day;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    this.set({day});
    try {
      const grid = await this.io.requestGrid(day, ac.signal);
      if (ac.signal.aborted) return;
      const cols = sgColsFor(grid.rows);
      const cells = grid.rows.map(r => Object.fromEntries(cols.map(c => [c.k, fmtv(r.values[c.k])])));
      this.set({
        loaded: true, rows: grid.rows, cols, cells, original: cells.map(row => ({...row})),
        reportDay: grid.report_day, focus: null, picked: new Set(),
      });
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Заправка не загрузилась: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  setDay(day: string) { this.set({day}); void this.load(); }
  setTime(time: string) { this.set({time}); }
  setFilter(filter: string) { this.set({filter}); }

  visibleRows(): number[] {
    return this.state.rows.map((r, i) => i).filter(i => sgInFilter(this.state.rows[i].loom, this.state.filter));
  }

  setFocus(r: number, c: number) { this.set({focus: {r, c}}); }

  typeCell(r: number, c: number, value: string) {
    const key = this.state.cols[c].k;
    const cells = this.state.cells.map((row, ri) => ri === r ? {...row, [key]: value} : row);
    this.set({cells});
  }

  // Прямая установка значения (протянуть/вставить/скопировать строку) — сразу канонизирует пряжу,
  // в отличие от обычного набора текста, где это происходит только при потере фокуса.
  setCellCanon(r: number, c: number, value: string) {
    const col = this.state.cols[c];
    const v = col.yarn ? yarnCanonicalize(value, this.io.yarns()) : value;
    const cells = this.state.cells.map((row, ri) => ri === r ? {...row, [col.k]: v} : row);
    this.set({cells});
  }

  commitCell(r: number, c: number) {
    const col = this.state.cols[c];
    if (!col.yarn) return;
    const cur = this.state.cells[r][col.k];
    const next = yarnCanonicalize(cur, this.io.yarns());
    if (next === cur) return;
    const cells = this.state.cells.map((row, ri) => ri === r ? {...row, [col.k]: next} : row);
    this.set({cells});
  }

  togglePick(r: number) {
    const picked = new Set(this.state.picked);
    if (picked.has(r)) picked.delete(r); else picked.add(r);
    this.set({picked});
  }

  toggleAllVisible(checked: boolean) {
    const visible = new Set(this.visibleRows());
    const picked = new Set(this.state.picked);
    if (checked) visible.forEach(r => picked.add(r)); else visible.forEach(r => picked.delete(r));
    this.set({picked});
  }

  fillFocusToPicked() {
    const f = this.state.focus;
    if (!f) return this.io.say('Сначала встаньте в ячейку, значение которой нужно протянуть', true);
    const picks = [...this.state.picked];
    if (!picks.length) return this.io.say('Отметьте станки галочками слева', true);
    const value = this.state.cells[f.r][this.state.cols[f.c].k];
    picks.forEach(r => this.setCellCanon(r, f.c, value));
    this.io.say(`${this.state.cols[f.c].t} = ${value || 'пусто'} — на ${picks.length} станков`);
  }

  copyRowToPicked() {
    const f = this.state.focus;
    if (!f) return this.io.say('Сначала встаньте в строку станка, которую нужно размножить', true);
    const picks = [...this.state.picked].filter(r => r !== f.r);
    if (!picks.length) return this.io.say('Отметьте станки галочками слева', true);
    const srcRow = this.state.cells[f.r];
    picks.forEach(r => this.state.cols.forEach((c, ci) => this.setCellCanon(r, ci, srcRow[c.k])));
    this.io.say(`Заправка ${this.state.rows[f.r].loom} скопирована на ${picks.length} станков`);
  }

  markSameCloth() {
    const f = this.state.focus;
    if (!f) return this.io.say('Сначала встаньте в строку станка', true);
    const cloth = this.state.rows[f.r].cloth;
    if (!cloth) return this.io.say('У этого станка нет кода ткани', true);
    const picked = new Set<number>();
    this.state.rows.forEach((r, i) => { if (r.cloth === cloth) picked.add(i); });
    this.set({picked});
    this.io.say(`Отмечены станки с кодом ткани ${cloth}`);
  }

  paste(r0: number, c0: number, text: string): number {
    const {cells, count, overflow} = applyPaste(this.state.cells, this.state.cols, r0, c0, text, this.visibleRows());
    this.set({cells});
    this.io.say(`Вставлено ячеек: ${count}` + (overflow ? ' — строк было больше, чем станков ниже' : ''));
    return count;
  }

  async save() {
    const bad = badYarnNames(this.state.cells, this.state.cols, this.io.yarns());
    if (bad.length) {
      if (!this.io.confirmDiscard(`Этой пряжи нет в справочнике: ${bad.join(', ')}.\nДобавить её в справочник и сохранить?`)) return;
      try {
        for (const name of bad) await this.io.postYarn({name});
        await this.io.refreshYarns();
      } catch (e) {
        this.io.say('Пряжа не добавилась: ' + (e instanceof Error ? e.message : String(e)), true);
        return;
      }
    }
    if (anyBad(this.state.cells, this.state.cols, this.io.yarns())) return this.io.say('Есть пряжа не из справочника — проверьте и сохраните ещё раз', true);
    const changed = rowsDirty(this.state.cells, this.state.original, this.state.cols);
    if (!changed.length) return this.io.say('Изменений нет');
    if (!this.state.time) return this.io.say('Укажите время начала заправки', true);
    const rows = changed.map(r => ({loom: this.state.rows[r].loom, values: this.state.cells[r]}));
    this.set({saving: true});
    try {
      const res = await this.io.confirmSetup({from_day: dash2dot(this.state.day), rows,
        effective_at: this.state.day + 'T' + this.state.time + ':00+05:00'});
      if (res) await this.load(true);
    } finally {
      this.set({saving: false});
    }
  }

  private async afterYarnsChanged() {
    await this.io.refreshYarns();
    if (this.state.loaded && !this.isDirty()) await this.load(true);
  }

  async addYarn(name: string, kind: string) {
    if (!name.trim()) return this.io.say('Напишите название пряжи', true);
    try {
      const r = await this.io.postYarn({name, kind});
      this.io.say(r.exists ? `«${r.name}» уже есть в справочнике` : `Добавлена пряжа «${r.name}»`);
      await this.afterYarnsChanged();
    } catch (e) {
      this.io.say('Не добавилась: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  async renameYarn(id: number, name: string) {
    try {
      await this.io.postYarnUpdate({id, name});
      this.io.say(`Пряжа переименована: ${name}`);
      await this.afterYarnsChanged();
    } catch (e) {
      this.io.say('Не сохранилось: ' + (e instanceof Error ? e.message : String(e)), true);
      await this.io.refreshYarns();
    }
  }

  async setYarnKind(id: number, kind: string) {
    try {
      await this.io.postYarnUpdate({id, kind});
      this.io.say('Вид пряжи сохранён');
      await this.afterYarnsChanged();
    } catch (e) {
      this.io.say('Не сохранилось: ' + (e instanceof Error ? e.message : String(e)), true);
      await this.io.refreshYarns();
    }
  }

  async toggleYarnActive(id: number, name: string, active: boolean) {
    try {
      await this.io.postYarnUpdate({id, active: !active});
      this.io.say(active ? `«${name}» скрыта` : `«${name}» снова в списке`);
      await this.afterYarnsChanged();
    } catch (e) {
      this.io.say('Не сохранилось: ' + (e instanceof Error ? e.message : String(e)), true);
      await this.io.refreshYarns();
    }
  }

  async importYarns(file: File) {
    try {
      const j = await this.io.uploadYarns(file);
      this.io.say(`Справочник 1С загружен: партий ${j.items} (новых ${j.new}, обновлено ${j.updated})` +
        (j.yarns_added.length ? `, новая пряжа: ${j.yarns_added.join(', ')}` : '') +
        (j.no_kind.length ? `. Без вида: ${j.no_kind.length}` : ''));
      await this.afterYarnsChanged();
    } catch (e) {
      this.io.say('Справочник не загрузился: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }
}
