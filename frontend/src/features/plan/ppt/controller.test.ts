import { afterEach, describe, expect, it, vi } from 'vitest';
import { PptController } from './controller';
import type { PptCheckData } from './model';

const data = (threshold = 5): PptCheckData => ({products: [{product_code: 'P1', orders: ['1557'], ppt_1c: 3300,
  ppt_fact: 3200, dev: -3, sec_1c: 4.2, norm_pct: 95, days: 4, clean_days: 3, looms: ['D1'], verdict: 'совпадает'}],
  days: [], threshold});
const deferred = () => {
  let resolve!: (v: unknown) => void, reject!: (v: unknown) => void;
  const promise = new Promise((a, b) => {resolve = a; reject = b;});
  return {promise, resolve, reject};
};
function setup() {
  const io = {request: vi.fn<(signal: AbortSignal) => Promise<PptCheckData>>(), changed: vi.fn()};
  const controller = new PptController(io);
  return {controller, io};
}

describe('PPT reconciliation', () => {
  it('loads the snapshot and marks it loaded', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValueOnce(data());
    await c.load();
    expect(c.state).toEqual({...data(), loaded: true});
  });

  it('cancels an older request and ignores its late response', async () => {
    const {controller: c, io} = setup(), a = deferred(), b = deferred();
    io.request.mockReturnValueOnce(a.promise as Promise<PptCheckData>).mockReturnValueOnce(b.promise as Promise<PptCheckData>);
    const first = c.load(), second = c.load();
    expect(io.request.mock.calls[0][0].aborted).toBe(true);
    b.resolve(data(9)); await second;
    a.resolve(data(1)); await first;
    expect(c.state.threshold).toBe(9);
  });

  it('keeps the last successful snapshot on a failed reload, matching legacy silence', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValueOnce(data());
    await c.load();
    io.request.mockRejectedValueOnce(new Error('403'));
    await c.load();
    expect(c.state).toEqual({...data(), loaded: true});
  });
});
