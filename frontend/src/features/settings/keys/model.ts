export type Scope = 'read' | 'write' | 'tickets';
export type ApiKey = {
  id: number; name: string; prefix: string; scopes: string; active: boolean;
  created_by: string; created_at: string | null; last_used_at: string | null;
};
export type KeysResponse = {keys: ApiKey[]; scopes: Record<string, string>};

export const ALL_SCOPES: Scope[] = ['read', 'write', 'tickets'];

export function scopesText(key: ApiKey, scopes: Record<string, string>): string {
  return key.scopes.split(' ').map(s => scopes[s] || s).join(', ');
}
