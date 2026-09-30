import { requestJson } from '../../report/http';
import type { KeysResponse, Scope } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestKeys(expire: () => void) {
  return requestJson<KeysResponse>('/api/keys', expire);
}
export function postKey(name: string, scopes: string[], expire: () => void) {
  return requestJson<{id: number; key: string; name: string; scopes: string[]}>('/api/keys', expire, {name, scopes});
}
export function postKeyRevoke(id: number, expire: () => void) {
  return requestJson<{ok: true}>('/api/keys/revoke', expire, {id});
}

export type KeysState = {
  loaded: boolean; keys: KeysResponse['keys']; scopes: KeysResponse['scopes'];
  name: string; selectedScopes: Set<Scope>; revealedKey: string | null;
};

export type KeysIO = {
  can: (perm: string) => boolean;
  requestKeys: () => Promise<KeysResponse>;
  postKey: (name: string, scopes: string[]) => Promise<{key: string}>;
  postRevoke: (id: number) => Promise<unknown>;
  confirmTranslated: (text: string) => boolean;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: KeysState = {loaded: false, keys: [], scopes: {}, name: '', selectedScopes: new Set(['read']), revealedKey: null};

export class KeysController {
  state: KeysState = initialState;
  private io: KeysIO;
  constructor(io: KeysIO) { this.io = io; }

  private set(next: Partial<KeysState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  async load() {
    if (!this.io.can('users')) return;
    try {
      const {keys, scopes} = await this.io.requestKeys();
      this.set({loaded: true, keys, scopes});
    } catch (e) {
      this.io.say('Ключи не загрузились: ' + message(e), true);
    }
  }

  setName(name: string) { this.set({name}); }
  toggleScope(scope: Scope) {
    const selectedScopes = new Set(this.state.selectedScopes);
    if (selectedScopes.has(scope)) selectedScopes.delete(scope); else selectedScopes.add(scope);
    this.set({selectedScopes});
  }

  async add() {
    try {
      const k = await this.io.postKey(this.state.name.trim(), [...this.state.selectedScopes]);
      this.set({revealedKey: k.key, name: ''});
      await this.load();
    } catch (e) {
      this.io.say('Ключ не выдан: ' + message(e), true);
    }
  }

  async revoke(id: number) {
    if (!this.io.confirmTranslated('Отозвать ключ? Программа, которая им пользуется, перестанет получать данные.')) return;
    try {
      await this.io.postRevoke(id);
      await this.load();
    } catch (e) {
      this.io.say('Не отозвался: ' + message(e), true);
    }
  }
}
