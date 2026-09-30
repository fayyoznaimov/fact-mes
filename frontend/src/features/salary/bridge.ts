import type { Operator } from './model';

export type SalaryBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  nf: (x: unknown, d?: number) => string;
  fday: (v: unknown) => string;
  operators: () => Operator[];
};

declare global {
  interface Window {
    FactSalaryLegacy?: SalaryBridge;
  }
}
