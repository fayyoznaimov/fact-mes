import { requestJson } from '../../report/http';
import type { AndonValues } from './model';
import { clampMinutes } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function postAndonSettings(values: AndonValues, expire: () => void) {
  return requestJson<{ok: true}>('/api/settings', expire, {
    andon_warn_min: values.warn, andon_alarm_min: values.alarm, andon_notify_min: values.notify,
  });
}

export type AndonState = AndonValues;

export type AndonIO = {
  postSettings: (values: AndonValues) => Promise<unknown>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

export class AndonController {
  state: AndonState = {warn: '', alarm: '', notify: ''};
  private io: AndonIO;
  constructor(io: AndonIO) { this.io = io; }

  private set(next: Partial<AndonState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  setValues(values: AndonValues) { this.set(values); }
  setWarn(warn: string) { this.set({warn}); }
  setAlarm(alarm: string) { this.set({alarm}); }
  setNotify(notify: string) { this.set({notify}); }

  async save() {
    const values: AndonValues = {
      warn: clampMinutes(this.state.warn), alarm: clampMinutes(this.state.alarm), notify: clampMinutes(this.state.notify),
    };
    try {
      await this.io.postSettings(values);
      this.set(values);
      this.io.say('Пороги андона сохранены — доски в цехе уже работают по ним');
    } catch (e) {
      this.io.say('Не сохранилось: ' + message(e), true);
    }
  }
}
