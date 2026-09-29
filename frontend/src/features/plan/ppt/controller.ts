import { requestJson } from '../../report/http';
import type { PptCheckData, PptDay, PptProduct } from './model';

export type PptState = {products: PptProduct[]; days: PptDay[]; threshold: number; loaded: boolean};
export type PptIO = {request: (signal: AbortSignal) => Promise<PptCheckData>; changed: () => void};

// Independent of React and DOM: one owner for the PPT-reconciliation snapshot.
export class PptController {
  state: PptState = {products: [], days: [], threshold: 0, loaded: false};
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;

  constructor(private io: PptIO) {}

  async load() {
    this.pending?.abort();
    if (this.disposed) return;
    const id = ++this.requestId, abort = new AbortController();
    this.pending = abort;
    try {
      const data = await this.io.request(abort.signal);
      if (id !== this.requestId || this.disposed) return;
      this.state = {products: data.products, days: data.days, threshold: data.threshold, loaded: true};
      this.io.changed();
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      // Без права смотреть план сервер отвечает ошибкой — легаси-поведение: сводка остаётся пустой, без сообщения.
      this.state = {...this.state, loaded: true};
      this.io.changed();
      void error;
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  dispose() { this.disposed = true; this.pending?.abort(); }
}

export async function requestPptCheck(signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<PptCheckData>('/api/ppt_check', expire, undefined, signal);
}
