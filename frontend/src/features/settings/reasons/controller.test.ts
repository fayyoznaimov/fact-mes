import { describe, expect, it, vi } from 'vitest';
import { ReasonsController } from './controller';
import type { ReasonsResponse } from './model';

const response: ReasonsResponse = {reasons: [], categories: {}, applies: {}};

function setup() {
  const io = {
    requestReasons: vi.fn<() => Promise<ReasonsResponse>>().mockResolvedValue(response),
    setReasonsData: vi.fn(),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new ReasonsController(io);
  return {controller, io};
}

describe('load', () => {
  it('fetches the reasons catalog', async () => {
    const {controller: c} = setup();
    await c.load();
    expect(c.state.loaded).toBe(true);
    expect(c.state.data).toEqual(response);
  });
  it('publishes the data to the legacy dialog, which still reads it directly', async () => {
    const {controller: c, io} = setup();
    await c.load();
    expect(io.setReasonsData).toHaveBeenCalledWith(response);
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.requestReasons.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('нет сети', true);
  });
});
