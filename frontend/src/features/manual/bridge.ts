export type ManualBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  nf: (x: unknown, d?: number) => string;
  fday: (v: unknown) => string;
  openTickets: () => void;
};

declare global {
  interface Window {
    FactManualLegacy?: ManualBridge;
  }
}
