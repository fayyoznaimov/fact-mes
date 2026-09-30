import { describe, expect, it, vi } from 'vitest';
import { KeysController } from './controller';
import type { KeysResponse } from './model';

const response: KeysResponse = {
  keys: [{id: 1, name: '1С', prefix: 'mes_abc', scopes: 'read', active: true, created_by: 'admin', created_at: '2026-09-01T00:00:00', last_used_at: null}],
  scopes: {read: 'читать данные', write: 'присылать заказы', tickets: 'тикеты'},
};

function setup(overrides: Record<string, unknown> = {}) {
  const io = {
    can: vi.fn().mockReturnValue(true),
    requestKeys: vi.fn<() => Promise<KeysResponse>>().mockResolvedValue(response),
    postKey: vi.fn<() => Promise<{key: string}>>().mockResolvedValue({key: 'mes_secret'}),
    postRevoke: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    confirmTranslated: vi.fn().mockReturnValue(true),
    changed: vi.fn(), say: vi.fn(),
    ...overrides,
  };
  const controller = new KeysController(io);
  return {controller, io};
}

describe('load', () => {
  it('refuses without the "users" permission', async () => {
    const {controller: c, io} = setup({can: vi.fn().mockReturnValue(false)});
    await c.load();
    expect(io.requestKeys).not.toHaveBeenCalled();
    expect(c.state.loaded).toBe(false);
  });
  it('fetches the key list and scope labels', async () => {
    const {controller: c} = setup();
    await c.load();
    expect(c.state.keys).toEqual(response.keys);
    expect(c.state.scopes).toEqual(response.scopes);
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.requestKeys.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Ключи не загрузились: нет сети', true);
  });
});

describe('toggleScope', () => {
  it('defaults to "read" selected', () => {
    const {controller: c} = setup();
    expect(c.state.selectedScopes).toEqual(new Set(['read']));
  });
  it('toggles scopes on and off', () => {
    const {controller: c} = setup();
    c.toggleScope('write');
    expect(c.state.selectedScopes).toEqual(new Set(['read', 'write']));
    c.toggleScope('read');
    expect(c.state.selectedScopes).toEqual(new Set(['write']));
  });
});

describe('add', () => {
  it('creates a key, reveals it, clears the name and reloads', async () => {
    const {controller: c, io} = setup();
    c.setName(' 1С боевой ');
    await c.add();
    expect(io.postKey).toHaveBeenCalledWith('1С боевой', ['read']);
    expect(c.state.revealedKey).toBe('mes_secret');
    expect(c.state.name).toBe('');
    expect(io.requestKeys).toHaveBeenCalledOnce();
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    io.postKey.mockRejectedValueOnce(new Error('назовите ключ'));
    await c.add();
    expect(io.say).toHaveBeenCalledWith('Ключ не выдан: назовите ключ', true);
  });
});

describe('revoke', () => {
  it('asks for confirmation before revoking', async () => {
    const {controller: c, io} = setup({confirmTranslated: vi.fn().mockReturnValue(false)});
    await c.revoke(1);
    expect(io.postRevoke).not.toHaveBeenCalled();
  });
  it('revokes and reloads on confirmation', async () => {
    const {controller: c, io} = setup();
    await c.revoke(1);
    expect(io.postRevoke).toHaveBeenCalledWith(1);
    expect(io.requestKeys).toHaveBeenCalledOnce();
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    io.postRevoke.mockRejectedValueOnce(new Error('нет прав'));
    await c.revoke(1);
    expect(io.say).toHaveBeenCalledWith('Не отозвался: нет прав', true);
  });
});
