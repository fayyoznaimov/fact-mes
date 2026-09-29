export type DashBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  nf: (x: unknown, d?: number) => string;
  fday: (v: unknown) => string;
};

declare global {
  interface Window {
    FactDashLegacy?: DashBridge;
  }
}
