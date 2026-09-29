// Общий мост между легаси-оболочкой (_app/ui.html) и React-версией вкладки «План».
// Один мост на все подвкладки: форматтеры дат/чисел и права у них общие.
export type PlanBridge = {
  can: (perm: string) => boolean;
  say: (text: string, isErr?: boolean) => void;
  esc: (s: unknown) => string;
  nf: (x: unknown, d?: number) => string;
  fday: (v: unknown) => string;
  ftime: (v: unknown) => string;
  dmy: (d: string) => string;
  expire: () => void;
  refreshPlan: () => void;
};

declare global {
  interface Window {
    FactPlanLegacy?: PlanBridge;
  }
}
