// Мост между легаси-оболочкой и React-версией вкладки «Заправка» (таблица + справочник пряжи).
// Справочник пряжи (YARNS/YARN_SLOTS) и выпадающий автокомплит (PICK) остаются в легаси —
// ими пользуется и уже перенесённое окно заправки станка (SetupDialog), и эта таблица:
// оба рендерят поля с data-pick="yarn:<место>"/"lot:<место>", которые ловит общий,
// не завязанный на владельца DOM, обработчик в _app/ui.html.
export type YarnRow = {id: number; name: string; key: string; kind: string; active: boolean};

export type SetupBridge = {
  can: (perm: string) => boolean;
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  fday: (v: unknown) => string;
  yarns: () => YarnRow[];
  refreshYarns: () => Promise<void>;
};

declare global {
  interface Window {
    FactSetupLegacy?: SetupBridge;
  }
}

export const tr = (text: string): string => (window.MesI18n ? window.MesI18n.t(text) : text);
