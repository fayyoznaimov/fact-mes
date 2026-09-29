import { requestJson } from '../report/http';
import type { Posted } from './bridge';
import type { ChipKind, DocFull, DocKindInfo, DocListItem, DocTab, LogOperation } from './model';

export function requestDocuments(kind: string, from: string, to: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<{documents: DocListItem[]; kinds: DocKindInfo[]}>(
    `/api/documents?${new URLSearchParams({type: kind, from, to})}`, expire, undefined, signal);
}
export function requestDocKinds(expire: () => void) {
  return requestJson<{kinds: DocKindInfo[]}>('/api/documents?limit=1', expire);
}
export function requestChangeLog(from: string, to: string, q: string, entity: string, expire: () => void, signal?: AbortSignal) {
  return requestJson<{operations: LogOperation[]; entities: {id: string; title: string}[]}>(
    `/api/change_log?${new URLSearchParams({from, to, q, entity})}`, expire, undefined, signal);
}
export function requestDoc(id: number, expire: () => void, signal?: AbortSignal) {
  return requestJson<DocFull>(`/api/documents/get?id=${encodeURIComponent(id)}`, expire, undefined, signal);
}
export type VerifyResult = {same: boolean; posted: {result: Record<string, unknown>}; now: {result: Record<string, unknown>}};
export function requestVerify(id: number, expire: () => void) {
  return requestJson<VerifyResult>(`/api/documents/verify?id=${id}`, expire);
}
export function postCancel(id: number, reason: string, expire: () => void) {
  return requestJson<{ok: true}>('/api/documents/cancel', expire, {id, reason});
}

export type DocsState = {
  kind: ChipKind;
  from: string; to: string; q: string; entity: string;
  entities: {id: string; title: string}[];
  kinds: Record<string, DocKindInfo>;
  items: DocListItem[];
  ops: LogOperation[];
  loadedList: boolean;
  sel: {type: 'doc'; id: number} | {type: 'op'; index: number} | null;
  doc: DocFull | null;
  loadingDoc: boolean;
  tab: DocTab;
  only: boolean;
  verify: {loading: boolean; same?: boolean; rows?: {title: string; before: number | null; after: number | null}[]; looms?: {loom: string; rows: {label: string; before: unknown; after: unknown; delta: number | null}[]}[]} | null;
};

export type DocsIO = {
  requestDocuments: (kind: string, from: string, to: string, signal: AbortSignal) => Promise<{documents: DocListItem[]; kinds: DocKindInfo[]}>;
  requestDocKinds: () => Promise<{kinds: DocKindInfo[]}>;
  requestChangeLog: (from: string, to: string, q: string, entity: string, signal: AbortSignal) => Promise<{operations: LogOperation[]; entities: {id: string; title: string}[]}>;
  requestDoc: (id: number, signal: AbortSignal) => Promise<DocFull>;
  requestVerify: (id: number) => Promise<VerifyResult>;
  postCancel: (id: number, reason: string) => Promise<unknown>;
  docConfirm: (type: string, payload: unknown) => Promise<Posted | null>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const todayIso = () => new Date(Date.now() + 5 * 3600e3 - 864e5).toISOString().slice(0, 10);

const initialState: DocsState = {
  kind: '', from: '', to: '', q: '', entity: '', entities: [], kinds: {},
  items: [], ops: [], loadedList: false, sel: null, doc: null, loadingDoc: false,
  tab: 'content', only: true, verify: null,
};

export class DocsController {
  state: DocsState = initialState;
  private io: DocsIO;
  private listAbort: AbortController | null = null;
  private docAbort: AbortController | null = null;
  private qTimer: ReturnType<typeof setTimeout> | null = null;
  constructor(io: DocsIO) { this.io = io; }

  private set(next: Partial<DocsState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  dispose() { this.listAbort?.abort(); this.docAbort?.abort(); if (this.qTimer) clearTimeout(this.qTimer); }

  setKind(kind: ChipKind) { this.set({kind, sel: null, doc: null}); void this.load(); }
  setFrom(from: string) { this.set({from}); void this.load(); }
  setTo(to: string) { this.set({to}); void this.load(); }
  setEntity(entity: string) { this.set({entity}); void this.load(); }
  setQ(q: string) {
    this.set({q});
    if (this.qTimer) clearTimeout(this.qTimer);
    this.qTimer = setTimeout(() => void this.load(), 250);
  }

  async load() {
    this.listAbort?.abort();
    const ac = new AbortController();
    this.listAbort = ac;
    try {
      if (this.state.kind === 'log') {
        const r = await this.io.requestChangeLog(this.state.from, this.state.to, this.state.q, this.state.entity, ac.signal);
        if (ac.signal.aborted) return;
        const entities = this.state.entities.length ? this.state.entities : r.entities;
        this.set({loadedList: true, ops: r.operations, entities});
        return;
      }
      const r = await this.io.requestDocuments(this.state.kind, this.state.from, this.state.to, ac.signal);
      if (ac.signal.aborted) return;
      const kinds = Object.fromEntries(r.kinds.map(k => [k.id, k]));
      const needle = this.state.q.trim().toLowerCase();
      const items = r.documents.filter(d => !needle || (d.search || '').toLowerCase().includes(needle));
      this.set({loadedList: true, items, kinds});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.io.say((e instanceof Error ? e.message : String(e)), true);
    }
  }

  private async ensureKinds() {
    if (Object.keys(this.state.kinds).length) return;
    try {
      const r = await this.io.requestDocKinds();
      this.set({kinds: Object.fromEntries(r.kinds.map(k => [k.id, k]))});
    } catch { /* доступно и без справочника видов — просто не покажем шапку действий */ }
  }

  async openDoc(id: number) {
    this.docAbort?.abort();
    const ac = new AbortController();
    this.docAbort = ac;
    this.set({sel: {type: 'doc', id}, doc: null, loadingDoc: true, tab: 'content', verify: null});
    try {
      const doc = await this.io.requestDoc(id, ac.signal);
      if (ac.signal.aborted) return;
      await this.ensureKinds();
      if (ac.signal.aborted) return;
      this.set({doc, loadingDoc: false});
    } catch (e) {
      if (ac.signal.aborted) return;
      this.set({loadingDoc: false});
      this.io.say((e instanceof Error ? e.message : String(e)), true);
    }
  }

  openOperation(index: number) { this.set({sel: {type: 'op', index}}); }

  setTab(tab: DocTab) { this.set({tab}); }
  setOnly(only: boolean) { this.set({only}); }

  async verify() {
    const doc = this.state.doc;
    if (!doc) return;
    this.set({verify: {loading: true}});
    try {
      const r = await this.io.requestVerify(doc.id);
      if (r.same) { this.set({verify: {loading: false, same: true}}); return; }
      if (doc.type === 'payroll') {
        const before = Object.fromEntries(((r.posted.result.operators as {operator_id: number; salary: number; name: string}[]) || []).map(o => [o.operator_id, o]));
        const after = Object.fromEntries(((r.now.result.operators as {operator_id: number; salary: number; name: string}[]) || []).map(o => [o.operator_id, o]));
        const ids = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter(id => (before[+id]?.salary) !== (after[+id]?.salary));
        const rows = ids.map(id => ({title: (after[+id] || before[+id]).name, before: before[+id] ? before[+id].salary : null, after: after[+id] ? after[+id].salary : null}));
        this.set({verify: {loading: false, same: false, rows}});
      } else {
        const before = Object.fromEntries(((r.posted.result.rows as {loom: string}[]) || []).map(x => [x.loom, x]));
        const after = Object.fromEntries(((r.now.result.rows as {loom: string}[]) || []).map(x => [x.loom, x]));
        const fieldDefs: [string, string][] = [['picks', 'Пики'], ['towels', 'Полотенца'], ['kg', 'Кг'], ['effic', 'КПД, %']];
        const looms = [...new Set([...Object.keys(before), ...Object.keys(after)])].map(loom => {
          const b = (before[loom] || {}) as Record<string, unknown>, a = (after[loom] || {}) as Record<string, unknown>;
          const rows = fieldDefs.filter(([f]) => b[f] !== a[f]).map(([f, label]) => ({label, before: b[f], after: a[f],
            delta: typeof b[f] === 'number' && typeof a[f] === 'number' ? (a[f] as number) - (b[f] as number) : null}));
          return {loom, rows};
        }).filter(x => x.rows.length);
        this.set({verify: {loading: false, same: false, looms}});
      }
    } catch (e) {
      this.io.say((e instanceof Error ? e.message : String(e)), true);
      this.set({verify: null});
    }
  }

  async cancel(reason: string) {
    const doc = this.state.doc;
    if (!doc) return;
    try {
      await this.io.postCancel(doc.id, reason);
      this.io.say('Документ ' + doc.number + ' отменён');
      await this.load();
      await this.openDoc(doc.id);
    } catch (e) {
      this.io.say('Не отменён: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  }

  async replace() {
    const doc = this.state.doc;
    if (!doc) return;
    const n = await this.io.docConfirm(doc.type, {from: doc.period_from, to: doc.period_to, supersedes_id: doc.id});
    if (n) { await this.load(); await this.openDoc(n.id); }
  }

  async newDoc(kind: 'payroll' | 'report') {
    const y = todayIso();
    const from = this.state.from || y.slice(0, 8).replace(/-/g, '.') + '01';
    const to = this.state.to || y.replace(/-/g, '.');
    const d = await this.io.docConfirm(kind, {from, to});
    if (d) { await this.load(); await this.openDoc(d.id); }
  }
}
