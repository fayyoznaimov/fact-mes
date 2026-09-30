export type TicketsBridge = {
  say: (text: string, isErr?: boolean) => void;
  expire: () => void;
  ftime: (v: unknown) => string;
};

declare global {
  interface Window {
    FactTicketsLegacy?: TicketsBridge;
  }
}
