export type OnecMessage = {
  id: number; received_at: string; who: string; action: string;
  order_numbers: string; ok: boolean; error?: string;
  result?: {cards?: number; yarns_added?: number} | null;
};
export type OnecDetail = {
  id: number; received_at: string; payload: unknown;
  result: unknown; error?: string;
};

export function outcomeText(m: OnecMessage): string {
  if (m.ok) return `принято: техкарт ${m.result ? m.result.cards : '—'}, новой пряжи ${m.result ? m.result.yarns_added || 0 : 0}`;
  return m.error || 'ошибка';
}
