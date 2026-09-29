import { requestJson } from '../../report/http';
import type { OnecDetail, OnecMessage } from './model';

export type OnecState = {messages: OnecMessage[]; loading: boolean; loaded: boolean};
export type OnecIO = {request: (signal: AbortSignal) => Promise<{messages: OnecMessage[]}>; changed: () => void};

// Independent of React and DOM: one owner for the message list and the pending request.
export class OnecController {
  state: OnecState = {messages: [], loading: false, loaded: false};
  private requestId = 0;
  private pending?: AbortController;
  private disposed = false;

  constructor(private io: OnecIO) {}

  async load() {
    this.pending?.abort();
    if (this.disposed) return;
    const id = ++this.requestId, abort = new AbortController();
    this.pending = abort;
    this.state = {...this.state, loading: true};
    this.io.changed();
    try {
      const data = await this.io.request(abort.signal);
      if (id !== this.requestId || this.disposed) return;
      this.state = {messages: data.messages, loading: false, loaded: true};
      this.io.changed();
    } catch (error) {
      if (id !== this.requestId || abort.signal.aborted || this.disposed) return;
      // Без права смотреть 1С-обмен сервер отвечает ошибкой — легаси-поведение: список остаётся пустым.
      this.state = {messages: [], loading: false, loaded: true};
      this.io.changed();
      void error;
    } finally {
      if (id === this.requestId) this.pending = undefined;
    }
  }

  dispose() { this.disposed = true; this.pending?.abort(); }
}

export async function requestOnecMessages(signal: AbortSignal | undefined, expire: () => void) {
  return requestJson<{messages: OnecMessage[]}>('/api/onec/messages?limit=50', expire, undefined, signal);
}
export async function requestOnecDetail(id: number, expire: () => void) {
  return requestJson<OnecDetail>('/api/onec/message?id=' + id, expire);
}
