import { describe, expect, it, vi } from 'vitest';
import { UsersController } from './controller';
import type { AccessCatalog, UserRow } from './model';

const catalog: AccessCatalog = {
  sections: [
    {id: 'plan', name: 'План', name_en: 'Plan'},
    {id: 'report', name: 'Отчёт', name_en: 'Report'},
    {id: 'users', name: 'Пользователи', name_en: 'Users'},
  ],
  permissions: [
    {id: 'plan_edit', name: 'Правка плана', name_en: 'Edit plan', sections: ['plan']},
    {id: 'users', name: 'Управление пользователями', name_en: 'Manage users', sections: ['users'], admin_only: true},
  ],
  role_defaults: {
    viewer: {sections: ['report'], permissions: []},
    master: {sections: ['plan', 'report'], permissions: ['plan_edit']},
    admin: {sections: ['plan', 'report', 'users'], permissions: ['plan_edit', 'users']},
  },
};

const row: UserRow = {id: 1, login: 'ivan', name: 'Иван', role: 'master', active: true, must_change: false,
  last_login: null, employee_id: null, sections: ['plan'], permissions: ['plan_edit'], access_mode: 'custom'};

function setup() {
  const io = {
    request: vi.fn<() => Promise<{users: UserRow[]; access_catalog: AccessCatalog}>>(),
    requestOperators: vi.fn<() => Promise<{operators: never[]}>>().mockResolvedValue({operators: []}),
    postUser: vi.fn<(body: unknown) => Promise<unknown>>().mockResolvedValue({ok: true}),
    postPassword: vi.fn<(body: unknown) => Promise<unknown>>().mockResolvedValue({ok: true}),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new UsersController(io);
  return {controller, io};
}

describe('load', () => {
  it('populates rows and the access catalog', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValueOnce({users: [row], access_catalog: catalog});
    await c.load();
    expect(c.state.loaded).toBe(true);
    expect(c.state.rows).toEqual([row]);
    expect(c.state.catalog).toEqual(catalog);
  });
  it('reports a load failure', async () => {
    const {controller: c, io} = setup();
    io.request.mockRejectedValueOnce(new Error('нет сети'));
    await c.load();
    expect(io.say).toHaveBeenCalledWith('Список пользователей не загрузился: нет сети', true);
  });
});

describe('dialog: role and mode', () => {
  it('opens a fresh dialog for a new user with the viewer role preset', async () => {
    const {controller: c} = setup();
    c.state = {...c.state, catalog};
    await c.openDialog(null);
    expect(c.state.dialog).toMatchObject({editId: null, role: 'viewer', mode: 'role', draft: null});
  });
  it('opens the dialog for an existing user with its saved custom draft', async () => {
    const {controller: c} = setup();
    c.state = {...c.state, catalog, rows: [row]};
    await c.openDialog(row);
    expect(c.state.dialog).toMatchObject({editId: 1, role: 'master', mode: 'custom',
      draft: {sections: ['plan'], permissions: ['plan_edit']}});
  });
  it('switching to admin forces mode back to role and clears the draft', async () => {
    const {controller: c} = setup();
    c.state = {...c.state, catalog, rows: [row]};
    await c.openDialog(row);
    c.setRole('admin');
    expect(c.state.dialog).toMatchObject({role: 'admin', mode: 'role', draft: null});
  });
  it('switching to custom mode seeds the draft from the role defaults', async () => {
    const {controller: c} = setup();
    c.state = {...c.state, catalog};
    await c.openDialog(null);
    c.setMode('custom');
    expect(c.state.dialog?.draft).toEqual(catalog.role_defaults.viewer);
  });
});

describe('dialog: access checkboxes', () => {
  it('toggling a section or permission mutates the draft, not the role defaults', async () => {
    const {controller: c} = setup();
    c.state = {...c.state, catalog};
    await c.openDialog(null);
    c.setMode('custom');
    c.togglePermission('plan_edit');
    expect(c.state.dialog?.draft).toEqual({sections: ['report', 'plan'], permissions: ['plan_edit']});
  });
});

describe('save', () => {
  it('rejects a new user without a login before calling the API', async () => {
    const {controller: c, io} = setup();
    c.state = {...c.state, catalog};
    await c.openDialog(null);
    const ok = await c.save('', 'Имя', 'longpassword', false);
    expect(ok).toBe(false);
    expect(io.postUser).not.toHaveBeenCalled();
    expect(c.state.dialog?.err).toBe('Нужен логин');
  });
  it('creates a user with role-preset access as null (server applies role defaults)', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValue({users: [], access_catalog: catalog});
    c.state = {...c.state, catalog};
    await c.openDialog(null);
    const ok = await c.save('ivan', 'Иван', 'longpassword', true);
    expect(ok).toBe(true);
    expect(io.postUser).toHaveBeenCalledWith({login: 'ivan', name: 'Иван', password: 'longpassword',
      must_change: true, role: 'viewer', access: null, employee_id: null});
    expect(c.state.dialog).toBeNull();
  });
  it('saves a custom access edit for an existing user', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValue({users: [row], access_catalog: catalog});
    c.state = {...c.state, catalog, rows: [row]};
    await c.openDialog(row);
    const ok = await c.save('ivan', 'Иван', '', false);
    expect(ok).toBe(true);
    expect(io.postUser).toHaveBeenCalledWith({id: 1, name: 'Иван', role: 'master',
      access: {sections: ['plan'], permissions: ['plan_edit']}, employee_id: null});
  });
});

describe('password dialog', () => {
  it('rejects a too-short password without calling the API', async () => {
    const {controller: c, io} = setup();
    c.openPassword(row);
    const ok = await c.savePassword('123', false);
    expect(ok).toBe(false);
    expect(io.postPassword).not.toHaveBeenCalled();
    expect(c.state.pw?.err).toBe('Пароль — не короче шести символов');
  });
  it('sets the password and closes the dialog', async () => {
    const {controller: c, io} = setup();
    c.openPassword(row);
    const ok = await c.savePassword('longpassword', true);
    expect(ok).toBe(true);
    expect(io.postPassword).toHaveBeenCalledWith({user_id: 1, password: 'longpassword', must_change: true});
    expect(io.say).toHaveBeenCalledWith('Пароль для ivan: longpassword — передайте его пользователю');
    expect(c.state.pw).toBeNull();
  });
});

describe('toggleActive', () => {
  it('flips active and reloads the list', async () => {
    const {controller: c, io} = setup();
    io.request.mockResolvedValue({users: [], access_catalog: catalog});
    await c.toggleActive(row);
    expect(io.postUser).toHaveBeenCalledWith({id: 1, active: false});
    expect(io.say).toHaveBeenCalledWith('ivan отключён');
  });
});
