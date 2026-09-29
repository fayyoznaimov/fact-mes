import { describe, expect, it, vi } from 'vitest';
import { CodesController } from './controller';

function setup() {
  const io = {changed: vi.fn(), postClothMap: vi.fn<(c: string, p: string) => Promise<void>>(),
    say: vi.fn(), refreshPlan: vi.fn()};
  const controller = new CodesController(io);
  return {controller, io};
}

describe('Codes state', () => {
  it('adopts the shared /api/plan payload pushed from the legacy loadPlan cascade', () => {
    const {controller: c} = setup();
    c.setData({unmapped: [{cloth: 'X1', variants: 1, looms: ['D1'], rows: 500, last_day: '2026-09-24'}],
      cloth_map: [{cloth_code: 'X2', product_code: 'P100'}]});
    expect(c.state.loaded).toBe(true);
    expect(c.state.unmapped).toHaveLength(1);
    expect(c.state.clothMap).toHaveLength(1);
  });
  it('defaults to empty arrays when fields are missing', () => {
    const {controller: c} = setup();
    c.setData({});
    expect(c.state).toEqual({unmapped: [], clothMap: [], loaded: true});
  });
});

describe('Linking a cloth code', () => {
  it('rejects an empty article without calling the API', async () => {
    const {controller: c, io} = setup();
    await c.link('X1', '');
    expect(io.postClothMap).not.toHaveBeenCalled();
    expect(io.say).toHaveBeenCalledWith('Укажите артикул 1С', true);
  });
  it('links, reports success and asks for a plan refresh', async () => {
    const {controller: c, io} = setup();
    io.postClothMap.mockResolvedValueOnce(undefined);
    await c.link('X1', 'P100');
    expect(io.postClothMap).toHaveBeenCalledWith('X1', 'P100');
    expect(io.say).toHaveBeenCalledWith('Связано: X1 = P100');
    expect(io.refreshPlan).toHaveBeenCalledOnce();
  });
  it('reports a failed link without refreshing the plan', async () => {
    const {controller: c, io} = setup();
    io.postClothMap.mockRejectedValueOnce(new Error('нет сети'));
    await c.link('X1', 'P100');
    expect(io.say).toHaveBeenCalledWith('Не связалось: нет сети', true);
    expect(io.refreshPlan).not.toHaveBeenCalled();
  });
});

describe('Unlinking a cloth code', () => {
  it('drops the mapping and refreshes without a success message, matching legacy', async () => {
    const {controller: c, io} = setup();
    io.postClothMap.mockResolvedValueOnce(undefined);
    await c.unlink('X2');
    expect(io.postClothMap).toHaveBeenCalledWith('X2', '');
    expect(io.say).not.toHaveBeenCalled();
    expect(io.refreshPlan).toHaveBeenCalledOnce();
  });
  it('reports a failed unlink without refreshing the plan', async () => {
    const {controller: c, io} = setup();
    io.postClothMap.mockRejectedValueOnce(new Error('сервер занят'));
    await c.unlink('X2');
    expect(io.say).toHaveBeenCalledWith('Не снялось: сервер занят', true);
    expect(io.refreshPlan).not.toHaveBeenCalled();
  });
});
