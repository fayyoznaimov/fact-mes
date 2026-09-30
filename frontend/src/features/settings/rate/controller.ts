import { requestJson } from '../../report/http';
import type { RatesResponse, Unit } from './model';
import { dash2dot } from './model';

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function requestRates(expire: () => void) {
  return requestJson<RatesResponse>('/api/rates', expire);
}

export type RateState = {loaded: boolean; periods: RatesResponse['periods']; from: string; rate: string; unit: Unit};

export type RateIO = {
  requestRates: () => Promise<RatesResponse>;
  confirmRate: (payload: {valid_from: string; rate: string; unit: string}) => Promise<{id: number} | null>;
  changed: () => void;
  say: (text: string, isErr?: boolean) => void;
};

const initialState: RateState = {loaded: false, periods: [], from: '', rate: '', unit: 'kpick'};

export class RateController {
  state: RateState = initialState;
  private io: RateIO;
  constructor(io: RateIO) { this.io = io; }

  private set(next: Partial<RateState>) { this.state = {...this.state, ...next}; this.io.changed(); }

  async load() {
    try {
      const r = await this.io.requestRates();
      this.set({
        loaded: true, periods: r.periods, rate: String(r.rate), unit: r.unit,
        from: this.state.from || r.day.replace(/\./g, '-'),
      });
    } catch (e) {
      this.io.say(message(e), true);
    }
  }

  setFrom(from: string) { this.set({from}); }
  setRate(rate: string) { this.set({rate}); }
  setUnit(unit: Unit) { this.set({unit}); }

  async save() {
    const r = await this.io.confirmRate({valid_from: dash2dot(this.state.from), rate: this.state.rate.trim(), unit: this.state.unit});
    if (r) await this.load();
  }
}
