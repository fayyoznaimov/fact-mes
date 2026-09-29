export type UserRow = {
  id: number; login: string; name: string; role: string; active: boolean;
  must_change: boolean; created_at?: string; last_login: string | null;
  employee_id: number | null; sections: string[]; permissions: string[];
  access_mode: 'role' | 'custom';
};

export type AccessItem = {
  id: string; name: string; name_en: string; legacy?: boolean;
  sections?: string[]; admin_only?: boolean;
};

export type AccessCatalog = {
  sections: AccessItem[];
  permissions: AccessItem[];
  role_defaults: Record<string, {sections: string[]; permissions: string[]}>;
};

export type Operator = {id: number; name: string; code: string; role: string; active: boolean};

export type AccessDraft = {sections: string[]; permissions: string[]};

// Пароль, который легко продиктовать: без похожих символов (0/O, 1/l/I).
export function genPassword(): string {
  const alphabet = 'abcdefghjkmnpqrstuvwxyz23456789';
  const random = crypto.getRandomValues(new Uint32Array(10));
  return [...random].map(x => alphabet[x % alphabet.length]).join('');
}

export function isPreset(role: string, mode: 'role' | 'custom'): boolean {
  return mode === 'role' || role === 'admin';
}

export function effectiveAccess(role: string, mode: 'role' | 'custom', draft: AccessDraft | null, catalog: AccessCatalog): AccessDraft {
  return isPreset(role, mode) ? catalog.role_defaults[role] : (draft || {sections: [], permissions: []});
}

export function forbiddenSection(item: AccessItem, admin: boolean): boolean {
  return item.id === 'users' && !admin;
}

export function forbiddenPermission(item: AccessItem, admin: boolean): boolean {
  return !!item.admin_only && !admin;
}

export function toggleSection(draft: AccessDraft, catalog: AccessCatalog, id: string): AccessDraft {
  const sections = draft.sections.includes(id) ? draft.sections.filter(x => x !== id) : [...draft.sections, id];
  const permissions = draft.permissions.filter(pid =>
    (catalog.permissions.find(p => p.id === pid)?.sections || []).some(s => sections.includes(s)));
  return {sections, permissions};
}

export function togglePermission(draft: AccessDraft, catalog: AccessCatalog, id: string): AccessDraft {
  const turningOn = !draft.permissions.includes(id);
  let sections = draft.sections;
  if (turningOn) {
    const item = catalog.permissions.find(p => p.id === id);
    const itemSections = item?.sections || [];
    if (!itemSections.some(s => sections.includes(s))) sections = [...sections, itemSections[0]];
  }
  const permissions = draft.permissions.includes(id) ? draft.permissions.filter(x => x !== id) : [...draft.permissions, id];
  const kept = permissions.filter(pid =>
    (catalog.permissions.find(p => p.id === pid)?.sections || []).some(s => sections.includes(s)));
  return {sections, permissions: kept};
}

export function accessSummary(row: UserRow): {mode: string; count: number} {
  return {
    mode: row.access_mode === 'custom' ? 'Индивидуально' : 'По шаблону роли',
    count: (row.sections || []).filter(x => !['bottle', 'kpi'].includes(x)).length,
  };
}

export function employeeOptions(operators: Operator[], rows: UserRow[], editingId: number | null, currentEmployeeId: number | null): Operator[] {
  const linked = new Set(rows.filter(x => x.employee_id && x.id !== editingId).map(x => x.employee_id));
  return operators.filter(o => o.role === 'master' && (o.active || o.id === currentEmployeeId) && !linked.has(o.id));
}

export function copySourceOptions(rows: UserRow[], editingId: number | null): UserRow[] {
  return rows.filter(x => x.id !== editingId);
}
