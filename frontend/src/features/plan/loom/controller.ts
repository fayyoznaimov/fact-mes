import { requestJson } from '../../report/http';
import type { Catalog, CatalogOrder, CellChange, LoomGrid, OrderFilter } from './model';
import { cellSnapshot, dash2dot, daysFrom, idxOf, key, orderByNo, split, topLeft, ymd } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export type Clipboard = {snap: {k: string; c: ReturnType<typeof cellSnapshot>}[]; from: string};
export type DialogRequest = {keys: string[]; forcedOrder?: string};
export type LoomState = {
  from: string; to: string; grid: LoomGrid | null; catalog: CatalogOrder[]; today: string;
  selection: Set<string>; anchor: string | null; focus: string | null; open: Set<string>;
  query: string; filter: OrderFilter; span: number; skipSundays: boolean;
  undoStack: CellChange[][]; clipboard: Clipboard | null; dialog: DialogRequest | null;
  loaded: boolean; uploading: boolean;
};
export type UploadResult = {from: string; to: string; looms: number; orders: {order_no: string}[]; notes: string[]};
export type LoomIO = {
  requestGrid: (from: string, to: string, signal: AbortSignal) => Promise<LoomGrid>;
  requestCatalog: (signal: AbortSignal) => Promise<Catalog>;
  postCells: (changes: CellChange[]) => Promise<{ok: number; picked?: {ambiguous?: number; nomatch?: number}; report_days: string[]}>;
  uploadExcel: (file: File) => Promise<UploadResult>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
  canEdit: () => boolean;
  dmy: (d: string) => string;
  refreshPlan: () => void;
};

// Independent of React and DOM: one owner for the loom×day grid, its selection/undo/clipboard,
// and every write action (place, move, copy, delete, dialog submit, Excel import).
export class LoomController {
  state: LoomState;
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;

  constructor(from: string, to: string, private io: LoomIO) {
    this.state = {
      from, to, grid: null, catalog: [], today: '', selection: new Set(), anchor: null, focus: null,
      open: new Set(), query: '', filter: 'all', span: 1, skipSundays: true,
      undoStack: [], clipboard: null, dialog: null, loaded: false, uploading: false,
    };
  }

  setRange(from: string, to: string) { this.state = {...this.state, from, to}; this.io.changed(); }
  setSpan(span: number) { this.state = {...this.state, span}; this.io.changed(); }
  setSkipSundays(v: boolean) { this.state = {...this.state, skipSundays: v}; this.io.changed(); }
  setQuery(q: string) { this.state = {...this.state, query: q}; this.io.changed(); }
  setFilter(f: OrderFilter) { this.state = {...this.state, filter: f}; this.io.changed(); }

  movePeriod(offset: number | null) {
    const g = this.state.grid;
    if (offset !== null && !g?.days.length) return;
    const a = offset === null ? new Date() : new Date(g!.days[0].replace(/\./g, '-') + 'T00:00');
    const b = offset === null ? new Date() : new Date(g!.days[g!.days.length - 1].replace(/\./g, '-') + 'T00:00');
    a.setDate(a.getDate() + (offset === null ? -3 : offset));
    b.setDate(b.getDate() + (offset === null ? 10 : offset));
    this.state = {...this.state, from: ymd(a), to: ymd(b)};
    void this.load();
  }

  async load() {
    this.pending?.abort();
    if (this.disposed) return;
    const id = ++this.requestId, abort = new AbortController();
    this.pending = abort;
    try {
      const [grid, catalog] = await Promise.all([
        this.io.requestGrid(dash2dot(this.state.from), dash2dot(this.state.to), abort.signal),
        this.io.requestCatalog(abort.signal),
      ]);
      if (id !== this.requestId || this.disposed) return;
      const looms = new Set(grid.looms.map(l => l.loom)), days = new Set(grid.days);
      const selection = new Set([...this.state.selection].filter(k => { const [l, d] = split(k); return looms.has(l) && days.has(d); }));
      this.state = {...this.state, grid, catalog: catalog.orders, today: ymd(new Date()), selection, loaded: true};
      this.io.changed();
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      this.io.say('План цеха не загрузился: ' + message(error), true);
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  click(k: string, mods: {shift: boolean; ctrl: boolean}) {
    const g = this.state.grid; if (!g) return;
    const looms = g.looms.map(l => l.loom), days = g.days;
    let selection = this.state.selection, anchor = this.state.anchor;
    if (mods.shift && anchor) {
      const [al, ad] = idxOf(anchor, looms, days), [bl, bd] = idxOf(k, looms, days);
      selection = new Set();
      for (let i = Math.min(al, bl); i <= Math.max(al, bl); i++)
        for (let j = Math.min(ad, bd); j <= Math.max(ad, bd); j++) selection.add(key(looms[i], days[j]));
    } else if (mods.ctrl) {
      selection = new Set(selection);
      if (selection.has(k)) selection.delete(k); else selection.add(k);
      anchor = k;
    } else { selection = new Set([k]); anchor = k; }
    const [l, d] = split(k);
    const c = g.looms.find(x => x.loom === l)?.cells[d];
    this.state = {...this.state, selection, anchor, focus: c?.order_no || null};
    this.io.changed();
  }

  clearSelection() { this.state = {...this.state, selection: new Set(), anchor: null, focus: null}; this.io.changed(); }
  setFocus(order: string | null) { this.state = {...this.state, focus: order}; this.io.changed(); }

  toggleOrderOpen(orderNo: string) {
    const open = new Set(this.state.open);
    if (open.has(orderNo)) open.delete(orderNo); else open.add(orderNo);
    this.state = {...this.state, open};
    this.io.changed();
  }

  clickOrderCard(orderNo: string, isProductLine: boolean) {
    if (isProductLine) { this.state = {...this.state, focus: orderNo}; this.io.changed(); return; }
    const focus = this.state.focus === orderNo ? null : orderNo;
    let open = this.state.open;
    if (focus) {
      const ord = orderByNo(this.state.catalog, orderNo);
      if (ord && ord.products.length > 1) { open = new Set(open); open.add(orderNo); }
    }
    this.state = {...this.state, focus, open};
    this.io.changed();
  }

  place(order: string, k: string, pc?: string | null) {
    const g = this.state.grid; if (!g) return;
    const [l, d] = split(k);
    const keys = this.state.selection.size > 1 && this.state.selection.has(k) ? [...this.state.selection]
      : daysFrom(d, Math.max(1, Math.min(90, this.state.span || 1)), this.state.skipSundays).map(x => key(l, x));
    const o = orderByNo(this.state.catalog, order);
    if (!pc && o && o.products.length > 1) { this.openDialog(k, {order, keys}); return; }
    if (!pc && o && o.products.length === 1) pc = o.products[0].product_code;
    void this.applyChanges(keys.map(x => { const [a, b] = split(x); return {loom: a, day: b, order_no: order, product_code: pc || null, note: null}; }));
  }

  snapshotKeys(keys: string[]): {k: string; c: ReturnType<typeof cellSnapshot>}[] {
    const g = this.state.grid; if (!g) return [];
    return keys.map(k => { const [l, d] = split(k); return {k, c: cellSnapshot(g.looms.find(x => x.loom === l)?.cells[d])}; });
  }

  dropCellOnCell(sourceKey: string, targetKey: string, move: boolean) {
    const keys = this.state.selection.size > 1 && this.state.selection.has(sourceKey) ? [...this.state.selection] : [sourceKey];
    this.block(this.snapshotKeys(keys), sourceKey, targetKey, move);
  }

  block(snap: {k: string; c: ReturnType<typeof cellSnapshot>}[], fromK: string, toK: string, move: boolean) {
    const g = this.state.grid; if (!g) return;
    const looms = g.looms.map(l => l.loom), days = g.days;
    const [fl, fd] = idxOf(fromK, looms, days), [tl, td] = idxOf(toK, looms, days);
    const dl = tl - fl, dd = td - fd;
    if (!dl && !dd) return;
    const out: CellChange[] = []; const dst = new Set<string>();
    snap.forEach(({k: kk, c}) => {
      const [li, di] = idxOf(kk, looms, days), L = looms[li + dl], D = days[di + dd];
      if (!L || !D) return;
      out.push({loom: L, day: D, ...c});
      dst.add(key(L, D));
    });
    if (move) snap.forEach(({k: kk}) => { if (!dst.has(kk)) { const [l, d] = split(kk); out.push({loom: l, day: d, order_no: null, note: null}); } });
    void this.applyChanges(out);
  }

  async applyChanges(changes: CellChange[], isUndo = false) {
    if (!this.io.canEdit()) { this.io.say('Доступен только просмотр плана', true); return; }
    const m = new Map<string, CellChange>(); changes.forEach(c => m.set(key(c.loom, c.day), c));
    changes = [...m.values()];
    if (!changes.length) return;
    const g = this.state.grid;
    const before: CellChange[] = changes.map(c => ({loom: c.loom, day: c.day, ...cellSnapshot(g?.looms.find(l => l.loom === c.loom)?.cells[c.day])}));
    try {
      const r = await this.io.postCells(changes);
      let undoStack = this.state.undoStack;
      if (!isUndo) { undoStack = [...undoStack, before]; if (undoStack.length > 50) undoStack = undoStack.slice(1); }
      this.state = {...this.state, undoStack};
      const amb = (r.picked?.ambiguous || 0) + (r.picked?.nomatch || 0);
      this.io.say((isUndo ? 'Отменено' : 'Сохранено') + `: клеток ${r.ok}`
        + (amb ? `; изделие не подобралось в ${amb} — выберите двойным щелчком` : '')
        + (r.report_days.length ? `; отчёт пересчитывается за ${r.report_days.map(this.io.dmy).join(', ')}` : ''), amb > 0);
      this.io.changed();
      await this.load();
    } catch (e) { this.io.say('Не сохранилось: ' + message(e), true); }
  }

  undo() {
    if (!this.io.canEdit()) return;
    const stack = [...this.state.undoStack], before = stack.pop();
    this.state = {...this.state, undoStack: stack};
    this.io.changed();
    if (before) void this.applyChanges(before, true);
  }

  deleteSelection() {
    const keys = [...this.state.selection]; if (!keys.length) return;
    void this.applyChanges(keys.map(k => { const [l, d] = split(k); return {loom: l, day: d, order_no: null, note: null}; }));
  }

  copySelection() {
    const keys = [...this.state.selection], g = this.state.grid; if (!keys.length || !g) return;
    this.state = {...this.state, clipboard: {snap: this.snapshotKeys(keys), from: topLeft(keys, g.looms.map(l => l.loom), g.days)}};
    this.io.say(`Скопировано клеток: ${keys.length}`);
    this.io.changed();
  }

  paste() {
    const keys = [...this.state.selection], g = this.state.grid;
    if (!keys.length || !this.state.clipboard || !g) return;
    this.block(this.state.clipboard.snap, this.state.clipboard.from, topLeft(keys, g.looms.map(l => l.loom), g.days), false);
  }

  openDialog(k: string, opts: {order?: string; keys?: string[]} = {}) {
    if (!this.io.canEdit()) return;
    const keys = opts.keys || (this.state.selection.size > 1 && this.state.selection.has(k) ? [...this.state.selection] : [k]);
    this.state = {...this.state, dialog: {keys, forcedOrder: opts.order}};
    this.io.changed();
  }
  closeDialog() { this.state = {...this.state, dialog: null}; this.io.changed(); }
  submitDialog(how: 'save' | 'clear', order: string, note: string, productCode: string) {
    const keys = this.state.dialog?.keys;
    this.state = {...this.state, dialog: null};
    this.io.changed();
    if (!keys) return;
    const clear = how === 'clear';
    const orderNo = clear ? null : order.trim() || null;
    const noteVal = clear ? null : note.trim() || null;
    const pc = clear ? null : productCode || null;
    void this.applyChanges(keys.map(x => { const [l, d] = split(x); return {loom: l, day: d, order_no: orderNo, product_code: pc, note: noteVal}; }));
  }

  async uploadExcel(file: File) {
    this.state = {...this.state, uploading: true}; this.io.changed();
    try {
      const j = await this.io.uploadExcel(file);
      this.io.say(`План загружен: ${this.io.dmy(j.from)}–${this.io.dmy(j.to)}, станков ${j.looms}, заказов ${j.orders.length}`
        + (j.notes.length ? `. Без изделия: ${j.notes.slice(0, 3).join('; ')}` : ''));
      this.io.refreshPlan();
    } catch (e) { this.io.say('План не загрузился: ' + message(e), true); }
    finally { this.state = {...this.state, uploading: false}; this.io.changed(); }
  }

  dispose() { this.disposed = true; this.pending?.abort(); }
}

export async function requestLoomGrid(from: string, to: string, signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<LoomGrid>(`/api/loom_plan?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`, expire, undefined, signal);
}
export async function requestLoomCatalog(signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<Catalog>('/api/loom_plan/catalog', expire, undefined, signal);
}
export async function requestSetCells(changes: CellChange[], expire: () => void) {
  return requestJson<{ok: number; picked?: {ambiguous?: number; nomatch?: number}; report_days: string[]}>(
    '/api/loom_plan/cells', expire, {changes});
}
export async function uploadLoomExcel(file: File, expire: () => void): Promise<UploadResult> {
  const response = await fetch('/api/loom_plan/upload', {method: 'POST', credentials: 'same-origin', body: file});
  if (response.status === 401) { expire(); throw new Error('сессия закончилась — войдите снова'); }
  const data = await response.json();
  if (data?.error || !response.ok) throw new Error(data?.error || `сервер ответил ошибкой ${response.status}`);
  return data;
}
