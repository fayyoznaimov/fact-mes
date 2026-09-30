import type { Me, Operator } from './model';

export type AssignBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  fday: (v: unknown) => string;
  ftime: (v: unknown) => string;
  can: (perm: string) => boolean;
  operators: () => Operator[];
  me: () => Me;
  confirmTranslated: (text: string) => boolean;
  openPrintWindow: (html: string) => void;
  openHistory: (day: string, shift: string) => void;
};

declare global {
  interface Window {
    FactAssignLegacy?: AssignBridge;
  }
}
