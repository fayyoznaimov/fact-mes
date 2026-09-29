import { requestJson } from '../../report/http';
import type { ClothMap, PlanClothData, UnmappedCloth } from './model';

export type CodesState = {unmapped: UnmappedCloth[]; clothMap: ClothMap[]; loaded: boolean};
export type CodesIO = {
  changed: () => void;
  postClothMap: (clothCode: string, productCode: string) => Promise<void>;
  say: (text: string, isErr?: boolean) => void;
  refreshPlan: () => void;
};
const message = (e: unknown) => e instanceof Error ? e.message : String(e);

// Independent of React and DOM: receives the shared /api/plan payload (pushed by the
// legacy loadPlan() cascade, same object it already fetches for the orders pane) and
// owns the cloth-code-mapping actions. No fetch of its own — one request feeds both panes.
export class CodesController {
  state: CodesState = {unmapped: [], clothMap: [], loaded: false};
  constructor(private io: CodesIO) {}

  setData(d: PlanClothData) {
    this.state = {unmapped: d.unmapped || [], clothMap: d.cloth_map || [], loaded: true};
    this.io.changed();
  }

  async link(cloth: string, product: string) {
    if (!product) {this.io.say('Укажите артикул 1С', true); return;}
    try {
      await this.io.postClothMap(cloth, product);
      this.io.say(`Связано: ${cloth} = ${product}`);
      this.io.refreshPlan();
    } catch (e) { this.io.say('Не связалось: ' + message(e), true); }
  }

  async unlink(cloth: string) {
    try {
      await this.io.postClothMap(cloth, '');
      this.io.refreshPlan();
    } catch (e) { this.io.say('Не снялось: ' + message(e), true); }
  }
}

export async function requestClothMap(clothCode: string, productCode: string, expire: () => void) {
  await requestJson('/api/plan/cloth_map', expire, {cloth_code: clothCode, product_code: productCode});
}
