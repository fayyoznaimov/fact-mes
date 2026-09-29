import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Ppt } from './Ppt';
import type { PptState } from './controller';
import { legacyFormatters, legacyPpt, pptMarkup, pptOutput } from '../../../test/legacyPlan';
import type { PlanBridge } from '../bridge';

const products = [
  {product_code: 'P1', orders: ['1557', '1558'], ppt_1c: 3300, ppt_fact: 3200, dev: -3.03, sec_1c: 4.2,
    norm_pct: 95, days: 4, clean_days: 3, looms: ['D1', 'D2'], verdict: 'совпадает'},
  {product_code: 'P2 <bad>', orders: [], ppt_1c: 3000, ppt_fact: null, dev: null, sec_1c: null,
    norm_pct: 82, days: 1, clean_days: 0, looms: [], verdict: 'проверьте PPT в 1С'},
];
const days = [
  {day: '2026-09-24', loom: 'D1', order_no: '1557', product_code: 'P1', ppt_1c: 3300, ppt_fact: 3200,
    dev: -3.03, rows: 5200, norm_pct: 95, time_eff: 97, rpm: 480, cloth: 'X144', verdict: 'ok', text: ''},
  {day: '2026-09-23', loom: 'D2', order_no: '1558', product_code: 'P1', ppt_1c: 3300, ppt_fact: 2900,
    dev: -12.1, rows: 400, norm_pct: 88, time_eff: 90, rpm: 470, cloth: 'X144', verdict: 'diff',
    text: 'расхождение — проверьте станок'},
];

function bridge(): PlanBridge {
  const f = legacyFormatters();
  return {can: () => true, say: vi.fn(), expire: vi.fn(), refreshPlan: vi.fn(), esc: f.esc, nf: f.nf, fday: f.fday, ftime: f.ftime, dmy: f.dmy};
}
function mount(state: PptState) {
  document.body.innerHTML = pptMarkup;
  const productsBody = document.querySelector('#ppt-prod tbody')!;
  const daysSummary = document.querySelector('#ppt-days-sum')!;
  const daysBody = document.querySelector('#ppt-days tbody')!;
  const daysDetails = document.querySelector<HTMLDetailsElement>('#ppt-days-box')!;
  [productsBody, daysSummary, daysBody].forEach(el => el.replaceChildren());
  render(<Ppt productsBody={productsBody as HTMLElement} daysSummary={daysSummary as HTMLElement}
    daysBody={daysBody as HTMLElement} daysDetails={daysDetails} state={state} bridge={bridge()}/>);
  return {productsBody, daysSummary, daysBody, daysDetails};
}
afterEach(() => {cleanup(); document.body.innerHTML = '';});

describe('Parity with the original PPT-reconciliation tables', () => {
  it('renders the per-product table exactly like the legacy renderer, days collapsed', async () => {
    mount({products, days, threshold: 5, loaded: true});
    expect(pptOutput(document)).toEqual(pptOutput(await legacyPpt({products, days, threshold: 5}, false)));
  });
  it('renders the per-day table too once the <details> has been opened', async () => {
    const {daysDetails} = mount({products, days, threshold: 5, loaded: true});
    daysDetails.open = true; fireEvent(daysDetails, new Event('toggle'));
    expect(pptOutput(document)).toEqual(pptOutput(await legacyPpt({products, days, threshold: 5}, true)));
  });
  it('shows the legacy empty-state row with no matching products', async () => {
    mount({products: [], days: [], threshold: 5, loaded: true});
    expect(pptOutput(document)).toEqual(pptOutput(await legacyPpt({products: [], days: [], threshold: 5}, false)));
  });
  it('keeps the static summary text before the first load, like the legacy markup', () => {
    mount({products: [], days: [], threshold: 0, loaded: false});
    expect(document.querySelector('#ppt-days-sum')?.textContent).toBe('По станкам и дням');
  });
});
