export type Posted = {id: number; number: string; after?: {days?: string[]; after_error?: string}};

export type DocsBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  // Общий диалог проверки/проведения документа (docDialog) используется и другими,
  // ещё не перенесёнными вкладками (Зарплата, Настройки) — переиспользуем как есть.
  docConfirm: (type: string, payload: unknown) => Promise<Posted | null>;
  goToRateSettings: () => void;
};

declare global {
  interface Window {
    FactDocsLegacy?: DocsBridge;
  }
}

export const tr = (text: string): string => (window.MesI18n ? window.MesI18n.t(text) : text);
