import { requestJson } from '../report/http';
import type { ImportFactResult, ImportResult, Operator } from './model';
import { importFactSummary, importSummary } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestOperators(expire: () => void) {
  return requestJson<{operators: Operator[]}>('/api/operators', expire);
}
export function postOperator(body: {id?: number; code: string; name: string; role: string; active?: boolean}, expire: () => void) {
  return requestJson<{ok: true}>('/api/operators', expire, body);
}
export function postOperatorDelete(id: number, expire: () => void) {
  return requestJson<{ok: true}>('/api/operators/delete', expire, {id});
}
export function postOperatorsImport(text: string, expire: () => void) {
  return requestJson<ImportResult>('/api/operators/import', expire, {text});
}
export function postOperatorsImportFact(expire: () => void) {
  return requestJson<ImportFactResult>('/api/operators/import_fact', expire, {});
}

export type PeopleForm = {code: string; name: string; role: string};
export type PeopleState = {
  operators: Operator[]; loaded: boolean; form: PeopleForm; pasteText: string; pasteResult: string;
};

export type PeopleIO = {
  operators: () => Operator[];
  requestOperators: () => Promise<{operators: Operator[]}>;
  postOperator: (body: {id?: number; code: string; name: string; role: string; active?: boolean}) => Promise<unknown>;
  postDelete: (id: number) => Promise<unknown>;
  postImport: (text: string) => Promise<ImportResult>;
  postImportFact: () => Promise<ImportFactResult>;
  confirmTranslated: (text: string) => boolean;
  setOperators: (operators: Operator[]) => void;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: PeopleState = {
  operators: [], loaded: false, form: {code: '', name: '', role: 'operator'}, pasteText: '', pasteResult: '',
};

export class PeopleController {
  state: PeopleState = initialState;
  private io: PeopleIO;
  constructor(io: PeopleIO) { this.io = io; }

  private set(next: Partial<PeopleState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  private setOperators(operators: Operator[]) {
    this.io.setOperators(operators);
    this.set({operators, loaded: true});
  }

  // Справочник загружает общий boot() при входе (нужен другим разделам ещё до
  // открытия «Операторов»); здесь только забираем уже готовый список.
  load() { this.set({operators: this.io.operators(), loaded: true}); }

  private async reload() {
    try {
      const {operators} = await this.io.requestOperators();
      this.setOperators(operators);
    } catch (e) {
      this.io.say('Справочник операторов не обновился: ' + message(e), true);
    }
  }

  setCode(code: string) { this.set({form: {...this.state.form, code}}); }
  setName(name: string) { this.set({form: {...this.state.form, name}}); }
  setRole(role: string) { this.set({form: {...this.state.form, role}}); }
  setPasteText(pasteText: string) { this.set({pasteText}); }

  async add() {
    const {code, name, role} = this.state.form;
    const c = code.trim(), n = name.trim();
    if (!c || !n) { this.io.say('Заполните код и имя', true); return; }
    try {
      await this.io.postOperator({code: c, name: n, role});
      this.set({form: {...this.state.form, code: '', name: ''}});
      await this.reload();
      this.io.say('Добавлен: ' + n);
    } catch (e) { this.io.say('Не добавился: ' + message(e), true); }
  }

  async setOperatorRole(id: number, role: string) {
    const o = this.state.operators.find(x => x.id === id);
    if (!o) return;
    try {
      await this.io.postOperator({id: o.id, code: o.code, name: o.name, role, active: !!o.active});
      this.setOperators(this.state.operators.map(x => x.id === id ? {...x, role} : x));
      this.io.say(`${o.name}: ${role}`);
    } catch (e) { this.io.say('Не сохранилось: ' + message(e), true); }
  }

  async remove(id: number) {
    if (!this.io.confirmTranslated('Удалить из справочника?')) return;
    try {
      await this.io.postDelete(id);
      await this.reload();
    } catch (e) { this.io.say('Не удалился: ' + message(e), true); }
  }

  async importPaste() {
    if (!this.state.pasteText.trim()) { this.io.say('Вставьте список', true); return; }
    try {
      const r = await this.io.postImport(this.state.pasteText);
      await this.reload();
      this.set({pasteText: '', pasteResult: importSummary(r)});
    } catch (e) { this.io.say('Не загрузилось: ' + message(e), true); }
  }

  async importFact() {
    try {
      const r = await this.io.postImportFact();
      await this.reload();
      this.io.say(importFactSummary(r));
    } catch (e) { this.io.say('Импорт не удался: ' + message(e), true); }
  }
}
