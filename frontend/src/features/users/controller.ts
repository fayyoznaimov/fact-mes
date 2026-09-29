import { requestJson } from '../report/http';
import type { AccessCatalog, AccessDraft, Operator, UserRow } from './model';
import { effectiveAccess, genPassword, toggleSection, togglePermission } from './model';

export function requestUsers(signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<{users: UserRow[]; access_catalog: AccessCatalog}>('/api/users', expire, undefined, signal);
}
export function requestOperators(expire: () => void) {
  return requestJson<{operators: Operator[]}>('/api/operators', expire);
}
export function postUser(body: unknown, expire: () => void) {
  return requestJson<{ok: true}>('/api/users', expire, body);
}
export function postPassword(body: unknown, expire: () => void) {
  return requestJson<{ok: true}>('/api/password', expire, body);
}

export type UserDialogState = {
  editId: number | null;
  login: string; loginLocked: boolean;
  name: string;
  role: string;
  mode: 'role' | 'custom';
  draft: AccessDraft | null;
  password: string;
  must: boolean;
  employeeId: string;
  err: string;
  saving: boolean;
};

export type PwDialogState = {
  userId: number; login: string; password: string; err: string; saving: boolean;
};

export type UsersState = {
  loaded: boolean;
  rows: UserRow[];
  catalog: AccessCatalog | null;
  operators: Operator[];
  dialog: UserDialogState | null;
  pw: PwDialogState | null;
};

export type UsersIO = {
  request: (signal: AbortSignal) => Promise<{users: UserRow[]; access_catalog: AccessCatalog}>;
  requestOperators: () => Promise<{operators: Operator[]}>;
  postUser: (body: unknown) => Promise<unknown>;
  postPassword: (body: unknown) => Promise<unknown>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: UsersState = {loaded: false, rows: [], catalog: null, operators: [], dialog: null, pw: null};

export class UsersController {
  state: UsersState = initialState;
  private abort: AbortController | null = null;
  private io: UsersIO;
  constructor(io: UsersIO) { this.io = io; }

  private set(next: Partial<UsersState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  async load() {
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    try {
      const d = await this.io.request(ac.signal);
      if (ac.signal.aborted) return;
      this.set({loaded: true, rows: d.users, catalog: d.access_catalog || this.state.catalog});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say('Список пользователей не загрузился: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  dispose() { this.abort?.abort(); }

  async openDialog(user: UserRow | null) {
    if (!this.state.operators.length) {
      try { const d = await this.io.requestOperators(); this.set({operators: d.operators}); }
      catch { /* справочник не критичен для открытия окна */ }
    }
    const draft: AccessDraft | null = user && user.access_mode === 'custom'
      ? {sections: [...user.sections], permissions: [...user.permissions]} : null;
    this.set({dialog: {
      editId: user ? user.id : null,
      login: user ? user.login : '', loginLocked: !!user,
      name: user ? user.name : '',
      role: user ? user.role : 'viewer',
      mode: user ? user.access_mode : 'role',
      draft,
      password: user ? '' : genPassword(),
      must: false,
      employeeId: user && user.employee_id ? String(user.employee_id) : '',
      err: '', saving: false,
    }});
  }

  closeDialog() { this.set({dialog: null}); }

  setRole(role: string) {
    if (!this.state.dialog) return;
    const mode = role === 'admin' ? 'role' : this.state.dialog.mode;
    this.set({dialog: {...this.state.dialog, role, mode, draft: null}});
  }

  setMode(mode: 'role' | 'custom') {
    if (!this.state.dialog || !this.state.catalog) return;
    const draft = mode === 'custom' && !this.state.dialog.draft
      ? structuredClone(this.state.catalog.role_defaults[this.state.dialog.role])
      : this.state.dialog.draft;
    this.set({dialog: {...this.state.dialog, mode, draft}});
  }

  toggleSection(id: string) {
    if (!this.state.dialog || !this.state.catalog) return;
    const draft = effectiveAccess(this.state.dialog.role, this.state.dialog.mode, this.state.dialog.draft, this.state.catalog);
    this.set({dialog: {...this.state.dialog, draft: toggleSection(draft, this.state.catalog, id)}});
  }

  togglePermission(id: string) {
    if (!this.state.dialog || !this.state.catalog) return;
    const draft = effectiveAccess(this.state.dialog.role, this.state.dialog.mode, this.state.dialog.draft, this.state.catalog);
    this.set({dialog: {...this.state.dialog, draft: togglePermission(draft, this.state.catalog, id)}});
  }

  setEmployeeId(employeeId: string) {
    if (!this.state.dialog) return;
    this.set({dialog: {...this.state.dialog, employeeId}});
  }

  copyFrom(sourceId: string) {
    if (!this.state.dialog) return;
    const src = this.state.rows.find(x => String(x.id) === sourceId);
    if (!src) return;
    const mode = src.role === 'admin' ? 'role' : src.access_mode;
    const draft: AccessDraft | null = src.role !== 'admin' && src.access_mode === 'custom'
      ? {sections: [...src.sections], permissions: [...src.permissions]} : null;
    this.set({dialog: {...this.state.dialog, role: src.role, mode, draft}});
    this.io.say(`Доступ взят у ${src.name} — проверьте и сохраните`);
  }

  async save(login: string, name: string, password: string, must: boolean) {
    const d = this.state.dialog;
    if (!d || !this.state.catalog) return false;
    const fail = (t: string) => { this.set({dialog: {...this.state.dialog!, err: t}}); return false; };
    if (!d.editId && !login) return fail('Нужен логин');
    if (!d.editId && password.length < 6) return fail('Пароль — не короче шести символов');
    const access = d.role === 'admin' || d.mode === 'role' ? null : effectiveAccess(d.role, d.mode, d.draft, this.state.catalog);
    if (access && !access.sections.length) return fail('Выберите хотя бы один раздел');
    const employeeId = d.role === 'master' && d.employeeId ? +d.employeeId : null;
    const body = d.editId
      ? {id: d.editId, name: name || login, role: d.role, access, employee_id: employeeId}
      : {login, name: name || login, password, must_change: must, role: d.role, access, employee_id: employeeId};
    this.set({dialog: {...d, saving: true}});
    try {
      await this.io.postUser(body);
      this.set({dialog: null});
      await this.load();
      this.io.say(d.editId ? 'Пользователь сохранён' : `Пользователь ${login} создан, пароль: ${password} — передайте его пользователю`);
      return true;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      this.set({dialog: {...this.state.dialog!, saving: false, err: message.charAt(0).toUpperCase() + message.slice(1)}});
      return false;
    }
  }

  async toggleActive(user: UserRow) {
    try {
      await this.io.postUser({id: user.id, active: !user.active});
      await this.load();
      this.io.say(user.active ? `${user.login} отключён` : `${user.login} включён`);
    } catch (e) {
      this.io.say(e instanceof Error ? e.message : String(e), true);
    }
  }

  openPassword(user: UserRow) {
    this.set({pw: {userId: user.id, login: user.login, password: genPassword(), err: '', saving: false}});
  }

  closePassword() { this.set({pw: null}); }

  async savePassword(password: string, must: boolean) {
    const pw = this.state.pw;
    if (!pw) return false;
    if (password.length < 6) { this.set({pw: {...pw, err: 'Пароль — не короче шести символов'}}); return false; }
    this.set({pw: {...pw, saving: true}});
    try {
      await this.io.postPassword({user_id: pw.userId, password, must_change: must});
      this.io.say(`Пароль для ${pw.login}: ${password} — передайте его пользователю`);
      this.set({pw: null});
      return true;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      this.set({pw: {...this.state.pw!, saving: false, err: 'Пароль не задан: ' + message}});
      return false;
    }
  }
}
