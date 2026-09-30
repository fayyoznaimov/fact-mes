import { requestJson } from '../report/http';
import type { AssignmentRow, Doc, DocSummary, Me, Operator, ShiftDoc } from './model';
import { buildPrintHtml, dash2dot, isLocked, nextSuggestIndex, ownMasterOf, searchOperators, selectedMasters, shiftNow, sortSuggestions, toRows, weekRange } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestShiftDoc(day: string, shift: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<ShiftDoc>(`/api/shift_doc?day=${day}&shift=${shift}`, expire, undefined, signal);
}
export function requestWeeklyDocs(from: string, to: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<{docs: DocSummary[]}>(`/api/shift_docs?from=${from}&to=${to}`, expire, undefined, signal);
}
export type SavePayload = {day: string; shift: string; assignments: AssignmentRow[]; masters: number[]; foreman_id: number | null; note: string};
export function postShiftDoc(payload: SavePayload, expire: () => void) {
  return requestJson<ShiftDoc>('/api/shift_doc', expire, payload);
}
export function postShiftDocConfirm(day: string, shift: string, confirmed: boolean, expire: () => void) {
  return requestJson<ShiftDoc>('/api/shift_doc/confirm', expire, {day, shift, confirmed});
}
export type FillResult = {from?: string; found?: number; assigned?: number; no_operator?: string[]; doc: ShiftDoc};
export function postShiftDocFill(day: string, shift: string, how: 'prev' | 'fact', expire: () => void) {
  return requestJson<FillResult>('/api/shift_doc/fill', expire, {day, shift, how});
}

export type Edits = {assignments: Record<string, number | null>; masters: number[]; foremanId: number | null; note: string};
export type AssignState = {
  day: string; shift: string; loaded: boolean;
  data: ShiftDoc | null; weekly: DocSummary[];
  checked: Set<string>; search: string; bulkId: string; suggestOpen: boolean; suggestIndex: number;
  edits: Edits;
};

export type AssignIO = {
  requestDoc: (day: string, shift: string, signal: AbortSignal) => Promise<ShiftDoc>;
  requestWeekly: (from: string, to: string, signal: AbortSignal) => Promise<{docs: DocSummary[]}>;
  postSave: (payload: SavePayload) => Promise<ShiftDoc>;
  postConfirm: (day: string, shift: string, confirmed: boolean) => Promise<ShiftDoc>;
  postFill: (day: string, shift: string, how: 'prev' | 'fact') => Promise<FillResult>;
  operators: () => Operator[];
  me: () => Me;
  confirmTranslated: (text: string) => boolean;
  fday: (v: unknown) => string;
  ftime: (v: unknown) => string;
  openPrintWindow: (html: string) => void;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: AssignState = {
  day: '', shift: '', loaded: false, data: null, weekly: [],
  checked: new Set(), search: '', bulkId: '', suggestOpen: false, suggestIndex: -1,
  edits: {assignments: {}, masters: [], foremanId: null, note: ''},
};

export class AssignController {
  state: AssignState = initialState;
  private abort: AbortController | null = null;
  private weeklyAbort: AbortController | null = null;
  private seq = 0;
  private io: AssignIO;
  private now: () => Date;
  constructor(io: AssignIO, now: () => Date = () => new Date()) { this.io = io; this.now = now; }

  private set(next: Partial<AssignState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.abort?.abort(); this.weeklyAbort?.abort(); }

  setDay(day: string) { this.set({day}); void this.load(); }
  setShift(shift: string) { this.set({shift}); void this.load(); }

  async load() {
    let {day, shift} = this.state;
    if (!day || !shift) {
      const n = shiftNow(this.now());
      day = day || n.day; shift = shift || n.shift;
      this.set({day, shift});
    }
    const seq = ++this.seq;
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const data = await this.io.requestDoc(dash2dot(day), shift, ac.signal);
      if (seq !== this.seq || ac.signal.aborted) return;
      const ownMaster = ownMasterOf(this.io.me());
      const locked = isLocked(data.doc);
      const edits: Edits = {
        assignments: Object.fromEntries(data.assignments.map(a => [a.loom, a.operator_id])),
        masters: selectedMasters(ownMaster, locked, data.masters),
        foremanId: data.doc?.foreman_id ?? null,
        note: data.doc?.note || '',
      };
      this.set({loaded: true, data, edits, checked: new Set()});
      void this.loadWeekly(dash2dot(day));
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Расстановка не загрузилась: ' + message(e), true);
    }
  }

  private async loadWeekly(dottedDay: string) {
    this.weeklyAbort?.abort();
    const ac = new AbortController();
    this.weeklyAbort = ac;
    const {from, to} = weekRange(dottedDay);
    try {
      const {docs} = await this.io.requestWeekly(from, to, ac.signal);
      if (ac.signal.aborted) return;
      this.set({weekly: docs});
    } catch {
      // список за неделю — вспомогательный, документ и без него работает
    }
  }

  openDoc(day: string, shift: string) { this.set({day, shift}); void this.load(); }

  toggleChecked(loom: string) {
    const checked = new Set(this.state.checked);
    if (checked.has(loom)) checked.delete(loom); else checked.add(loom);
    this.set({checked});
  }

  toggleAllChecked(checked: boolean, editable: boolean) {
    if (!editable) return;
    const looms = this.state.data?.assignments.map(a => a.loom) || [];
    this.set({checked: checked ? new Set(looms) : new Set()});
  }

  setSearch(search: string) { this.set({search, bulkId: '', suggestOpen: true, suggestIndex: -1}); }
  openSuggestions() { this.set({suggestOpen: true}); }
  closeSuggestions() { this.set({suggestOpen: false, suggestIndex: -1}); }

  suggestionList(): Operator[] {
    return sortSuggestions(searchOperators(this.io.operators(), this.state.search), this.state.search);
  }

  moveSuggestion(dir: 1 | -1) {
    const opening = !this.state.suggestOpen;
    const ops = this.suggestionList();
    this.set({
      suggestOpen: true,
      suggestIndex: nextSuggestIndex(opening ? -1 : this.state.suggestIndex, ops.length, dir),
    });
  }

  pickOperator(op: Operator) { this.set({search: op.code, bulkId: String(op.id), suggestOpen: false, suggestIndex: -1}); }

  applyBulk() {
    const {search, bulkId, checked} = this.state;
    if (search.trim() && !bulkId) { this.io.say('Выберите оператора из списка', true); return; }
    const id = bulkId ? +bulkId : null;
    const assignments = {...this.state.edits.assignments};
    checked.forEach(loom => { assignments[loom] = id; });
    this.set({edits: {...this.state.edits, assignments}, checked: new Set()});
  }

  setOperator(loom: string, id: number | null) {
    this.set({edits: {...this.state.edits, assignments: {...this.state.edits.assignments, [loom]: id}}});
  }

  toggleMaster(id: number) {
    const masters = this.state.edits.masters.includes(id)
      ? this.state.edits.masters.filter(x => x !== id) : [...this.state.edits.masters, id];
    this.set({edits: {...this.state.edits, masters}});
  }

  setForeman(id: number | null) { this.set({edits: {...this.state.edits, foremanId: id}}); }
  setNote(note: string) { this.set({edits: {...this.state.edits, note}}); }

  private collect(): SavePayload {
    return {
      day: dash2dot(this.state.day), shift: this.state.shift,
      assignments: toRows(this.state.edits.assignments),
      masters: this.state.edits.masters,
      foreman_id: this.state.edits.foremanId,
      note: this.state.edits.note,
    };
  }

  async save() {
    try {
      await this.io.postSave(this.collect());
      this.io.say(`Расстановка смены ${this.state.shift} сохранена`);
      await this.load();
    } catch (e) { this.io.say('Не сохранилось: ' + message(e), true); }
  }

  async confirm() {
    const locked = isLocked(this.state.data?.doc ?? null);
    try {
      if (!locked) await this.io.postSave(this.collect());
      await this.io.postConfirm(dash2dot(this.state.day), this.state.shift, !locked);
      this.io.say(locked ? 'Документ открыт для правки' : `Расстановка смены ${this.state.shift} утверждена`);
      await this.load();
    } catch (e) { this.io.say('Не получилось: ' + message(e), true); }
  }

  async fill(how: 'prev' | 'fact') {
    const text = how === 'fact' ? 'Заполнить расстановку по данным FACT? То, что на экране, заменится.'
      : 'Взять расстановку из прошлой такой же смены? То, что на экране, заменится.';
    if (!this.io.confirmTranslated(text)) return;
    try {
      const r = await this.io.postFill(dash2dot(this.state.day), this.state.shift, how);
      this.io.say(how === 'fact'
        ? `Из FACT: станков ${r.found}, назначено ${r.assigned}` + (r.no_operator?.length ? `; нет в справочнике: ${r.no_operator.length}` : '')
        : `Взято из смены ${this.state.shift} за ${this.io.fday(r.from)}`);
      await this.load();
    } catch (e) { this.io.say('Не заполнилось: ' + message(e), true); }
  }

  print() {
    const data = this.state.data;
    if (!data) return;
    const html = buildPrintHtml({
      day: dash2dot(this.state.day), shift: this.state.shift, hours: data.hours,
      doc: data.doc as Doc, assignments: this.collect().assignments,
      masters: this.state.edits.masters, foremanId: this.state.edits.foremanId, note: this.state.edits.note,
      operators: this.io.operators(),
    }, this.io.fday, this.io.ftime);
    this.io.openPrintWindow(html);
  }
}
