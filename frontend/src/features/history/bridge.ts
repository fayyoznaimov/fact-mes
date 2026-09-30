export type HistoryBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
};

declare global {
  interface Window {
    FactHistoryLegacy?: HistoryBridge;
  }
}
