import { describe, expect, it, vi } from 'vitest';
import { TicketsController } from './controller';
import type { LiveResponse, Ticket, TicketsResponse } from './model';

const ticket: Ticket = {
  id: 1, loom: 'D1', started_at: '2026-09-25T08:00:00', ended_at: null, duration_sec: 600,
  fact_cause: 'Manual', style: null, shift: '2026.09.25.A', category_id: null, comment: null,
  opened_by: null, classified_by: null, classified_at: null, escalated_at: null,
  reason: 'Ручной останов', reason_from: 'FACT', cause_ru: 'Ручной останов', category_name: null, open: true,
};
const response: TicketsResponse = {tickets: [ticket], categories: [], can_edit: true};
const live: LiveResponse = {looms: [], totals: {stopped: 2}};

function setup() {
  const io = {
    requestTickets: vi.fn<() => Promise<TicketsResponse>>().mockResolvedValue(response),
    requestLive: vi.fn<() => Promise<LiveResponse>>().mockResolvedValue(live),
    postNew: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    postClose: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    postClassify: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new TicketsController(io, () => new Date('2026-09-25T10:00:00'));
  return {controller, io};
}

describe('load', () => {
  it('defaults from/to to the current production day', async () => {
    const {controller: c, io} = setup();
    await c.load();
    expect(c.state.from).toBe('2026-09-25');
    expect(c.state.to).toBe('2026-09-25');
    expect(io.requestTickets).toHaveBeenCalledWith('2026.09.25', '2026.09.25', false, expect.anything());
  });
  it('loads tickets and live data together', async () => {
    const {controller: c} = setup();
    await c.load();
    expect(c.state.tickets).toEqual([ticket]);
    expect(c.state.canEdit).toBe(true);
    expect(c.state.live).toEqual(live);
  });
  it('asks the server for open-only tickets when the filter is "open"', async () => {
    const {controller: c, io} = setup();
    c.setFilter('open');
    await Promise.resolve(); await Promise.resolve();
    expect(io.requestTickets).toHaveBeenCalledWith(expect.any(String), expect.any(String), true, expect.anything());
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.requestTickets.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Тикеты не загрузились: нет сети', true);
  });
});

describe('setShift / setLooms', () => {
  it('reset pagination without reloading from the server', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.showMore();
    expect(c.state.show).toBe(200);
    c.setShift('B');
    expect(c.state.show).toBe(100);
    expect(io.requestTickets).toHaveBeenCalledTimes(1);
  });
});

describe('toggleSort', () => {
  it('resets pagination and flips the sort', () => {
    const {controller: c} = setup();
    c.showMore();
    c.toggleSort('started_at');
    expect(c.state.sort).toEqual({k: 'started_at', dir: 1});
    expect(c.state.show).toBe(100);
  });
});

describe('newTicket', () => {
  it('refuses without edit rights', async () => {
    const {controller: c, io} = setup();
    await c.load();
    c.state.canEdit = false;
    await c.newTicket('D1');
    expect(io.say).toHaveBeenCalledWith('Нет прав заводить тикеты', true);
    expect(io.postNew).not.toHaveBeenCalled();
  });
  it('creates a ticket and reloads', async () => {
    const {controller: c, io} = setup();
    await c.load();
    await c.newTicket('D1');
    expect(io.postNew).toHaveBeenCalledWith('D1');
    expect(io.requestTickets).toHaveBeenCalledTimes(2);
  });
});

describe('closeTicket', () => {
  it('closes and reloads', async () => {
    const {controller: c, io} = setup();
    await c.closeTicket(1);
    expect(io.postClose).toHaveBeenCalledWith(1);
    expect(io.requestTickets).toHaveBeenCalledOnce();
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    io.postClose.mockRejectedValueOnce(new Error('нет прав'));
    await c.closeTicket(1);
    expect(io.say).toHaveBeenCalledWith('Не закрылся: нет прав', true);
  });
});

describe('category dialog', () => {
  it('opens with the picked ticket and closes on demand', () => {
    const {controller: c} = setup();
    c.openCategoryDialog(ticket);
    expect(c.state.pick).toBe(ticket);
    c.closeCategoryDialog();
    expect(c.state.pick).toBeNull();
  });
  it('classifies the picked ticket, closes the dialog and reloads', async () => {
    const {controller: c, io} = setup();
    c.openCategoryDialog(ticket);
    await c.pickCategory('electric');
    expect(io.postClassify).toHaveBeenCalledWith(1, 'electric', null);
    expect(c.state.pick).toBeNull();
    expect(io.say).toHaveBeenCalledWith('D1: причина записана');
    expect(io.requestTickets).toHaveBeenCalledOnce();
  });
  it('closes the dialog and reports a failure without blocking further edits', async () => {
    const {controller: c, io} = setup();
    io.postClassify.mockRejectedValueOnce(new Error('уже занято'));
    c.openCategoryDialog(ticket);
    await c.pickCategory('electric');
    expect(c.state.pick).toBeNull();
    expect(io.say).toHaveBeenCalledWith('Не записалось: уже занято', true);
  });
  it('does nothing when no ticket is picked', async () => {
    const {controller: c, io} = setup();
    await c.pickCategory('electric');
    expect(io.postClassify).not.toHaveBeenCalled();
  });
});
