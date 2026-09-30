import { describe, expect, it, vi } from 'vitest';
import { RateController } from './controller';
import type { RatesResponse } from './model';

const response: RatesResponse = {
  day: '2026.09.25', rate: 287, unit: 'kpick',
  periods: [{id: 1, valid_from: '2026.09.01', rate: 287, unit: 'kpick', doc_id: 5, set_by: 'admin', set_at: '2026-09-01T10:00:00', number: 'СТ-1', status: 'posted'}],
};

function setup() {
  const io = {
    requestRates: vi.fn<() => Promise<RatesResponse>>().mockResolvedValue(response),
    confirmRate: vi.fn<() => Promise<{id: number} | null>>().mockResolvedValue({id: 2}),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new RateController(io);
  return {controller, io};
}

describe('load', () => {
  it('seeds the form from the response and defaults the day when empty', async () => {
    const {controller: c} = setup();
    await c.load();
    expect(c.state.rate).toBe('287');
    expect(c.state.unit).toBe('kpick');
    expect(c.state.from).toBe('2026-09-25');
    expect(c.state.periods).toEqual(response.periods);
  });
  it('keeps a day the user already picked', async () => {
    const {controller: c} = setup();
    c.setFrom('2026-09-20');
    await c.load();
    expect(c.state.from).toBe('2026-09-20');
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.requestRates.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('нет сети', true);
  });
});

describe('save', () => {
  it('confirms the new rate and reloads on success', async () => {
    const {controller: c, io} = setup();
    c.setFrom('2026-09-20'); c.setRate(' 300 '); c.setUnit('pick');
    await c.save();
    expect(io.confirmRate).toHaveBeenCalledWith({valid_from: '2026.09.20', rate: '300', unit: 'pick'});
    expect(io.requestRates).toHaveBeenCalledOnce();
  });
  it('does not reload when the confirmation is cancelled', async () => {
    const {controller: c, io} = setup();
    io.confirmRate.mockResolvedValueOnce(null);
    await c.save();
    expect(io.requestRates).not.toHaveBeenCalled();
  });
});
