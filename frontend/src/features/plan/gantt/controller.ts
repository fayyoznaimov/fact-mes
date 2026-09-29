import { requestJson } from '../../report/http';
import { addDays, isoOf, monday } from './model';
import type { GanttData, TimelineData } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export type GanttState = {from: string; days: number; group: string; data: GanttData | null};
export type GanttIO = {request: (from: string, to: string, signal: AbortSignal) => Promise<GanttData>; changed: () => void; say: (t: string, isErr?: boolean) => void};

// Independent of React and DOM: owns the visible period, the group filter and the fetched snapshot.
export class GanttController {
  state: GanttState = {from: monday(), days: 7, group: '', data: null};
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;

  constructor(private io: GanttIO) {}

  loadOnce() { if (!this.state.data) void this.load(); }
  setDays(days: number) { this.state = {...this.state, days}; void this.load(); }
  setGroup(group: string) { this.state = {...this.state, group}; this.io.changed(); }
  prev() { this.state = {...this.state, from: addDays(this.state.from, -this.state.days)}; void this.load(); }
  next() { this.state = {...this.state, from: addDays(this.state.from, this.state.days)}; void this.load(); }
  today() { this.state = {...this.state, from: monday()}; void this.load(); }

  async load() {
    this.pending?.abort();
    if (this.disposed) return;
    const id = ++this.requestId, abort = new AbortController();
    this.pending = abort;
    try {
      const to = addDays(this.state.from, this.state.days - 1);
      const data = await this.io.request(this.state.from, to, abort.signal);
      if (id !== this.requestId || this.disposed) return;
      this.state = {...this.state, data};
      this.io.changed();
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      this.io.say('Ганта не загрузилась: ' + message(error), true);
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  dispose() { this.disposed = true; this.pending?.abort(); }
}

export type TimelineState = {loom: string; a: string; b: string; data: TimelineData};
export type TimelineIO = {request: (loom: string, from: string, to: string, signal: AbortSignal) => Promise<TimelineData>; changed: () => void; say: (t: string, isErr?: boolean) => void};

// Independent of React and DOM: owns the currently-open stop-detail snapshot (±8h stepping keeps it alive after close).
export class TimelineController {
  state: TimelineState | null = null;
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;

  constructor(private io: TimelineIO) {}

  async open(loom: string, a: string, b: string) {
    this.pending?.abort();
    if (this.disposed) return;
    const id = ++this.requestId, abort = new AbortController();
    this.pending = abort;
    try {
      const data = await this.io.request(loom, a, b, abort.signal);
      if (id !== this.requestId || this.disposed) return;
      this.state = {loom, a, b, data};
      this.io.changed();
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      this.io.say('Остановы не загрузились: ' + message(error), true);
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  step(hours: number) {
    if (!this.state) return;
    const shift = (t: string) => isoOf(new Date(Date.parse(t) + hours * 3600e3));
    void this.open(this.state.loom, shift(this.state.a), shift(this.state.b));
  }

  close() { this.state = null; this.io.changed(); }
  dispose() { this.disposed = true; this.pending?.abort(); }
}

export async function requestGantt(from: string, to: string, signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<GanttData>(`/api/gantt?from=${from}&to=${to}`, expire, undefined, signal);
}
export async function requestLoomTimeline(loom: string, from: string, to: string, signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<TimelineData>(`/api/loom_timeline?loom=${encodeURIComponent(loom)}&from=${from}&to=${to}`, expire, undefined, signal);
}
