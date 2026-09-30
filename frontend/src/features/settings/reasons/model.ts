export type Reason = {
  id: string; name: string; en: string; reason: string; applies: string; call: boolean;
  category: string; color: string | null; sort: number; in_operator: boolean; in_analytics: boolean;
  important: boolean; active: boolean; builtin: boolean;
};
export type ReasonsResponse = {reasons: Reason[]; categories: Record<string, string>; applies: Record<string, string>};

export function categoryLabel(r: ReasonsResponse, id: string): string {
  return r.categories[id] || id;
}
export function appliesLabel(r: ReasonsResponse, id: string): string {
  return r.applies[id] || id;
}
export function places(r: Reason): ('в цеху' | 'при разборе')[] {
  const out: ('в цеху' | 'при разборе')[] = [];
  if (r.in_operator) out.push('в цеху');
  if (r.in_analytics) out.push('при разборе');
  return out;
}
