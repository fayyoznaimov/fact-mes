export type Operator = {id: number; code: string; name: string; role: string; active: number | boolean};

export const ROLE_RU: Record<string, string> = {operator: 'оператор', master: 'мастерица', foreman: 'мастер'};
export function roleLabel(role: string): string { return ROLE_RU[role] || role; }

export type ImportResult = {in_list: number; added: number; updated: number; same: number; repeats: number; skipped: string[]};
export function importSummary(r: ImportResult): string {
  return `В списке ${r.in_list} человек: добавлено ${r.added}, обновлено ${r.updated}, без изменений ${r.same}`
    + (r.repeats ? `; повторов ${r.repeats}` : '')
    + (r.skipped.length ? `; не разобрано строк ${r.skipped.length}: ${r.skipped.slice(0, 3).join(' | ')}` : '');
}

export type ImportFactResult = {found: number; added: number; total: number};
export function importFactSummary(r: ImportFactResult): string {
  return `Найдено имён в FACT: ${r.found}, добавлено новых: ${r.added}, всего в справочнике: ${r.total}`;
}
