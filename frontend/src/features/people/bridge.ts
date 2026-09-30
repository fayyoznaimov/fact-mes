import type { Operator } from './model';

export type PeopleBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  can: (perm: string) => boolean;
  operators: () => Operator[];
  setOperators: (operators: Operator[]) => void;
  confirmTranslated: (text: string) => boolean;
};

declare global {
  interface Window {
    FactPeopleLegacy?: PeopleBridge;
  }
}
