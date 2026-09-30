// Общий мост между легаси-оболочкой (_app/ui.html) и React-версией вкладки
// «Настройки»: один мост на все панели (ставка, причины, андон, ключи).
export type ConfirmedDoc = {id: number; number: string; after?: {days?: string[]; after_error?: string}} | null;

export type SettingsBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  fday: (v: unknown) => string;
  ftime: (v: unknown) => string;
  nf: (x: unknown, d?: number) => string;
  can: (perm: string) => boolean;
  confirmTranslated: (text: string) => boolean;
  confirmRate: (payload: {valid_from: string; rate: string; unit: string}) => Promise<ConfirmedDoc>;
  openReasonDialog: (id: string) => void;
  showReasonChanges: () => void;
  setReasonsData: (data: {reasons: unknown[]; categories: Record<string, string>; applies: Record<string, string>}) => void;
};

declare global {
  interface Window {
    FactSettingsLegacy?: SettingsBridge;
  }
}
