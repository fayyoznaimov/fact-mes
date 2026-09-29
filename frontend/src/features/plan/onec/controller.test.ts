import { afterEach, describe, expect, it, vi } from 'vitest';
import { OnecController } from './controller';
import type { OnecMessage } from './model';

const msg = (id: number): OnecMessage => ({id, received_at: '', who: '', action: '', order_numbers: '', ok: true});
const deferred = () => {
  let resolve!: (v: unknown) => void, reject!: (v: unknown) => void;
  const promise = new Promise((a, b) => {resolve = a; reject = b;});
  return {promise, resolve, reject};
};
function setup() {
  const io = {request: vi.fn<(signal: AbortSignal) => Promise<{messages: OnecMessage[]}>>(), changed: vi.fn()};
  const controller = new OnecController(io);
  return {controller, io};
}
afterEach(() => vi.unstubAllGlobals());

describe('Onec messages', () => {
  it('loads messages and marks the list as loaded', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValueOnce({messages: [msg(1)]});
    await c.load();
    expect(c.state).toEqual({messages: [msg(1)], loading: false, loaded: true});
    expect(io.changed).toHaveBeenCalled();
  });

  it('cancels an older request and ignores its late response', async () => {
    const {controller: c, io} = setup(), a = deferred(), b = deferred();
    io.request.mockReturnValueOnce(a.promise as Promise<{messages: OnecMessage[]}>)
      .mockReturnValueOnce(b.promise as Promise<{messages: OnecMessage[]}>);
    const first = c.load(), second = c.load();
    expect(io.request.mock.calls[0][0].aborted).toBe(true);
    b.resolve({messages: [msg(2)]}); await second;
    a.resolve({messages: [msg(1)]}); await first;
    expect(c.state.messages).toEqual([msg(2)]);
  });

  it('falls back to an empty list without a permission error, matching legacy silence', async () => {
    const {controller: c, io} = setup();
    io.request.mockRejectedValueOnce(new Error('403'));
    await c.load();
    expect(c.state).toEqual({messages: [], loading: false, loaded: true});
  });

  it('ignores a stale rejection after a later request already started', async () => {
    const {controller: c, io} = setup(), a = deferred(), b = deferred();
    io.request.mockReturnValueOnce(a.promise as Promise<{messages: OnecMessage[]}>)
      .mockReturnValueOnce(b.promise as Promise<{messages: OnecMessage[]}>);
    const first = c.load(), second = c.load();
    a.reject(new Error('old')); await first;
    b.resolve({messages: [msg(3)]}); await second;
    expect(c.state.messages).toEqual([msg(3)]);
  });

  it('stops updating state after dispose', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValueOnce({messages: [msg(1)]});
    const pending = c.load();
    c.dispose();
    await pending;
    expect(c.state.loaded).toBe(false);
  });
});
