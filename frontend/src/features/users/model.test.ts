import { describe, expect, it } from 'vitest';
import type { AccessCatalog, UserRow } from './model';
import {
  accessSummary, copySourceOptions, effectiveAccess, employeeOptions,
  forbiddenPermission, forbiddenSection, isPreset, togglePermission, toggleSection,
} from './model';

const catalog: AccessCatalog = {
  sections: [
    {id: 'plan', name: 'План', name_en: 'Plan'},
    {id: 'report', name: 'Отчёт', name_en: 'Report'},
    {id: 'users', name: 'Пользователи', name_en: 'Users'},
  ],
  permissions: [
    {id: 'plan_edit', name: 'Правка плана', name_en: 'Edit plan', sections: ['plan']},
    {id: 'export', name: 'Выгрузка', name_en: 'Export', sections: ['report']},
    {id: 'users', name: 'Управление пользователями', name_en: 'Manage users', sections: ['users'], admin_only: true},
  ],
  role_defaults: {
    viewer: {sections: ['report'], permissions: []},
    admin: {sections: ['plan', 'report', 'users'], permissions: ['plan_edit', 'export', 'users']},
  },
};

describe('isPreset / effectiveAccess', () => {
  it('is preset when mode is role, or the role is admin regardless of mode', () => {
    expect(isPreset('viewer', 'role')).toBe(true);
    expect(isPreset('viewer', 'custom')).toBe(false);
    expect(isPreset('admin', 'custom')).toBe(true);
  });
  it('returns the role defaults when preset, or the draft otherwise', () => {
    expect(effectiveAccess('viewer', 'role', null, catalog)).toEqual(catalog.role_defaults.viewer);
    expect(effectiveAccess('viewer', 'custom', {sections: ['plan'], permissions: []}, catalog))
      .toEqual({sections: ['plan'], permissions: []});
    expect(effectiveAccess('viewer', 'custom', null, catalog)).toEqual({sections: [], permissions: []});
  });
});

describe('forbidden checkboxes', () => {
  it('locks the users section/permission to non-admins, as the server also enforces', () => {
    const usersSection = catalog.sections.find(s => s.id === 'users')!;
    const usersPerm = catalog.permissions.find(p => p.id === 'users')!;
    expect(forbiddenSection(usersSection, false)).toBe(true);
    expect(forbiddenSection(usersSection, true)).toBe(false);
    expect(forbiddenPermission(usersPerm, false)).toBe(true);
    expect(forbiddenPermission(usersPerm, true)).toBe(false);
  });
});

describe('toggleSection', () => {
  it('drops permissions whose sections are no longer selected', () => {
    const draft = {sections: ['plan', 'report'], permissions: ['plan_edit', 'export']};
    expect(toggleSection(draft, catalog, 'plan')).toEqual({sections: ['report'], permissions: ['export']});
  });
  it('adds a section back without touching permissions', () => {
    const draft = {sections: ['report'], permissions: ['export']};
    expect(toggleSection(draft, catalog, 'plan')).toEqual({sections: ['report', 'plan'], permissions: ['export']});
  });
});

describe('togglePermission', () => {
  it('auto-selects the permission\'s first section when none of them are checked yet', () => {
    const draft = {sections: [], permissions: []};
    expect(togglePermission(draft, catalog, 'plan_edit')).toEqual({sections: ['plan'], permissions: ['plan_edit']});
  });
  it('does not add a section that is already covered', () => {
    const draft = {sections: ['plan'], permissions: []};
    expect(togglePermission(draft, catalog, 'plan_edit')).toEqual({sections: ['plan'], permissions: ['plan_edit']});
  });
  it('turns a permission back off without touching sections', () => {
    const draft = {sections: ['plan'], permissions: ['plan_edit']};
    expect(togglePermission(draft, catalog, 'plan_edit')).toEqual({sections: ['plan'], permissions: []});
  });
});

const rows: UserRow[] = [
  {id: 1, login: 'a', name: 'A', role: 'master', active: true, must_change: false, last_login: null,
    employee_id: 5, sections: ['plan'], permissions: [], access_mode: 'role'},
  {id: 2, login: 'b', name: 'B', role: 'master', active: true, must_change: false, last_login: null,
    employee_id: null, sections: ['plan', 'bottle'], permissions: [], access_mode: 'custom'},
];

describe('accessSummary', () => {
  it('reports mode and section count excluding the always-on legacy sections', () => {
    expect(accessSummary(rows[0])).toEqual({mode: 'По шаблону роли', count: 1});
    expect(accessSummary(rows[1])).toEqual({mode: 'Индивидуально', count: 1});
  });
});

describe('employeeOptions', () => {
  const operators = [
    {id: 5, name: 'Мастерица 1', code: 'M1', role: 'master', active: true},
    {id: 6, name: 'Мастерица 2', code: 'M2', role: 'master', active: true},
    {id: 7, name: 'Бывшая', code: 'M3', role: 'master', active: false},
    {id: 8, name: 'Оператор', code: 'O1', role: 'operator', active: true},
  ];
  it('excludes non-masters and operators already linked to another user', () => {
    expect(employeeOptions(operators, rows, null, null).map(o => o.id)).toEqual([6]);
  });
  it('keeps the currently linked operator visible even when editing that same user', () => {
    expect(employeeOptions(operators, rows, 1, 5).map(o => o.id)).toEqual([5, 6]);
  });
  it('keeps an inactive operator visible only if it is the one currently linked', () => {
    expect(employeeOptions(operators, rows, 3, 7).map(o => o.id)).toEqual([6, 7]);
  });
});

describe('copySourceOptions', () => {
  it('excludes the user being edited from the copy-from list', () => {
    expect(copySourceOptions(rows, 1).map(x => x.id)).toEqual([2]);
    expect(copySourceOptions(rows, null).map(x => x.id)).toEqual([1, 2]);
  });
});
