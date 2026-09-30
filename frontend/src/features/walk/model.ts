export type Shift = {day: string; shift: string};
export type WalkRow = {
  loom: string; style: string; eff: number; stop_min: number;
  weft_ct: number; top_ct: number; warp_ct: number; manual_ct: number; wait_min: number;
  idle: boolean; main: string; main_min: number;
};
export type WalkResponse = {day: string; shift: string; rows: WalkRow[]};

export function shiftLabel(fday: (v: unknown) => string, s: Shift): string {
  return `${fday(s.day)} · смена ${s.shift}`;
}

export function styleText(style: string): string | null {
  return style && style !== 'Undefined' ? style : null;
}
