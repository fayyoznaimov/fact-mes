export type UnmappedCloth = {cloth: string; variants: number; looms: string[]; rows: number; last_day: string};
export type ClothMap = {cloth_code: string; product_code: string; set_by?: string};
export type PlanClothData = {unmapped?: UnmappedCloth[]; cloth_map?: ClothMap[]};
