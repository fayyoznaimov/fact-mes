import { requestJson } from '../../report/http';
import type { ReasonsResponse } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestReasons(expire: () => void) {
  return requestJson<ReasonsResponse>('/api/reasons', expire);
}

export type ReasonsState = {loaded: boolean; data: ReasonsResponse | null};

export type ReasonsIO = {
  requestReasons: () => Promise<ReasonsResponse>;
  setReasonsData: (data: ReasonsResponse) => void;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

export class ReasonsController {
  state: ReasonsState = {loaded: false, data: null};
  private io: ReasonsIO;
  constructor(io: ReasonsIO) { this.io = io; }

  private set(next: Partial<ReasonsState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  async load() {
    try {
      const data = await this.io.requestReasons();
      // Диалог добавления/правки причины пока не перенесён и читает эти
      // данные из старой глобальной переменной — держим её в курсе.
      this.io.setReasonsData(data);
      this.set({loaded: true, data});
    } catch (e) {
      this.io.say(message(e), true);
    }
  }
}
