export type AndonValues = {warn: string; alarm: string; notify: string};

export function clampMinutes(v: string): string {
  return String(Math.max(0, parseInt(v, 10) || 0));
}
