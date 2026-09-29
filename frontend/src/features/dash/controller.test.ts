import { describe, expect, it, vi } from 'vitest';
import { DashController } from './controller';
import type { DashResponse, ForecastResponse } from './model';

const dashboard: DashResponse = {
  totals: {running: 1, stopped: 1, with_ticket: 0, kpicks: 10, weft_ct: 0, warp_ct: 0, top_ct: 0,
    with_plan: 2, looms: 2, with_product: 2, with_operator: 2},
  mismatches: [],
  rows: [{loom: 'D1', state: 'run', kpicks: 5, towels: 1, weft_ct: 0, warp_ct: 0, top_ct: 0, cloth: 'X1'},
    {loom: 'D2', state: 'stop', kpicks: 5, towels: 1, weft_ct: 0, warp_ct: 0, top_ct: 0, cloth: 'X1'}],
  articles: [], yarn_titles: {},
};

function setup() {
  const io = {
    requestDashboard: vi.fn<() => Promise<DashResponse>>().mockResolvedValue(dashboard),
    requestForecast: vi.fn<() => Promise<ForecastResponse>>().mockResolvedValue({events: []}),
    postLoomArticle: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new DashController(io);
  return {controller, io};
}

describe('setDays', () => {
  it('defaults to the first (most recent) day when none is selected yet', () => {
    const {controller: c} = setup();
    c.setDays(['2026.09.24', '2026.09.23']);
    expect(c.state.day).toBe('2026.09.24');
  });
  it('keeps the current day if it is still in the new list', () => {
    const {controller: c} = setup();
    c.setDays(['2026.09.24', '2026.09.23']);
    c.setDay('2026.09.23');
    c.setDays(['2026.09.24', '2026.09.23', '2026.09.22']);
    expect(c.state.day).toBe('2026.09.23');
  });
});

describe('load', () => {
  it('fetches the dashboard for the current day and shift', async () => {
    const {controller: c, io} = setup();
    c.setDay('2026.09.24'); c.setShift('A');
    await c.load();
    expect(io.requestDashboard).toHaveBeenCalledWith('2026.09.24', 'A', expect.anything());
    expect(c.state.data).toEqual(dashboard);
  });
  it('drops a stale response that resolves after a newer request started', async () => {
    const {controller: c, io} = setup();
    let resolveFirst!: (v: DashResponse) => void;
    io.requestDashboard.mockReturnValueOnce(new Promise(r => {resolveFirst = r;}));
    const first = c.load();
    io.requestDashboard.mockResolvedValueOnce({...dashboard, totals: {...dashboard.totals, running: 99}});
    const second = c.load();
    await second;
    resolveFirst(dashboard);
    await first;
    expect(c.state.data?.totals.running).toBe(99);
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.requestDashboard.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Дашборд не загрузился: нет сети', true);
  });
});

describe('cardsHref', () => {
  it('includes the shift only when one is picked', () => {
    const {controller: c} = setup();
    c.setDay('2026.09.24');
    expect(c.cardsHref()).toBe('/cards?day=2026.09.24');
    c.setShift('B');
    expect(c.cardsHref()).toBe('/cards?day=2026.09.24&shift=B');
  });
});

describe('toggleOpen', () => {
  it('tracks expanded setup rows independently per loom', () => {
    const {controller: c} = setup();
    c.toggleOpen('D1');
    expect(c.state.open.has('D1')).toBe(true);
    c.toggleOpen('D2');
    c.toggleOpen('D1');
    expect(c.state.open).toEqual(new Set(['D2']));
  });
});

describe('setArticle', () => {
  it('posts the article and reloads the dashboard on success', async () => {
    const {controller: c, io} = setup();
    c.setDay('2026.09.24');
    await c.setArticle('D1', 'ART1');
    expect(io.postLoomArticle).toHaveBeenCalledWith('D1', 'ART1', '2026.09.24');
    expect(io.say).toHaveBeenCalledWith('D1: заправлено ART1');
    expect(io.requestDashboard).toHaveBeenCalledOnce();
  });
  it('reports removal with a different message when the article is cleared', async () => {
    const {controller: c, io} = setup();
    await c.setArticle('D1', '');
    expect(io.say).toHaveBeenCalledWith('D1: артикул снят');
  });
  it('reports a failure without reloading', async () => {
    const {controller: c, io} = setup();
    io.postLoomArticle.mockRejectedValueOnce(new Error('нет прав'));
    await c.setArticle('D1', 'ART1');
    expect(io.say).toHaveBeenCalledWith('Не сохранилось: нет прав', true);
    expect(io.requestDashboard).not.toHaveBeenCalled();
  });
});
