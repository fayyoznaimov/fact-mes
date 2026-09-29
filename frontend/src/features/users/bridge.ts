// Мост между легаси-оболочкой (_app/ui.html) и React-версией вкладки «Пользователи».
export type UsersBridge = {
  can: (perm: string) => boolean;
  say: (text: string, isErr?: boolean) => void;
  ftime: (v: unknown) => string;
  expire: () => void;
  roles: () => Record<string, string>;
};

declare global {
  interface Window {
    FactUsersLegacy?: UsersBridge;
    MesI18n?: {t: (s: string) => string; language: string; setLanguage: (l: string) => void};
  }
}

export const tr = (text: string): string => (window.MesI18n ? window.MesI18n.t(text) : text);
