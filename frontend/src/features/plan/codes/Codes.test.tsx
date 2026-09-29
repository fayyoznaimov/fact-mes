import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Codes } from './Codes';
import type { CodesState } from './controller';
import { codesMarkup, codesOutput, legacyCodes, legacyFormatters } from '../../../test/legacyPlan';
import type { PlanBridge } from '../bridge';

const unmapped = [
  {cloth: 'X144', variants: 3, looms: ['D1', 'D2'], rows: 5200, last_day: '2026-09-24'},
  {cloth: '<bad>', variants: 1, looms: ['J1'], rows: 40, last_day: ''},
];
const clothMap = [{cloth_code: 'X100', product_code: 'P100 < & "', set_by: 'Мастер'}, {cloth_code: 'X101', product_code: 'P101'}];

function bridge(): PlanBridge {
  const f = legacyFormatters();
  return {can: () => true, say: vi.fn(), expire: vi.fn(), refreshPlan: vi.fn(), esc: f.esc, nf: f.nf, fday: f.fday, ftime: f.ftime, dmy: f.dmy};
}
function mount(state: CodesState, link = vi.fn(), unlink = vi.fn()) {
  document.body.innerHTML = codesMarkup;
  const unmappedBody = document.querySelector('#cm-unmapped tbody')!;
  const mapBody = document.querySelector('#cm-map tbody')!;
  unmappedBody.replaceChildren(); mapBody.replaceChildren();
  const b = bridge();
  render(<Codes unmappedBody={unmappedBody as HTMLElement} mapBody={mapBody as HTMLElement} state={state} bridge={b} link={link} unlink={unlink}/>);
  return {unmappedBody, mapBody, bridge: b, link, unlink};
}
afterEach(() => {cleanup(); document.body.innerHTML = '';});

describe('Parity with the original cloth-code tables', () => {
  it('renders unmapped codes and linked codes exactly like the legacy renderer', () => {
    mount({unmapped, clothMap, loaded: true});
    expect(codesOutput(document)).toEqual(codesOutput(legacyCodes({unmapped, cloth_map: clothMap}).doc));
  });
  it('shows both legacy empty-state rows once loaded with nothing to show', () => {
    mount({unmapped: [], clothMap: [], loaded: true});
    expect(codesOutput(document)).toEqual(codesOutput(legacyCodes({unmapped: [], cloth_map: []}).doc));
  });
  it('stays empty before the first plan push, like the legacy tbody', () => {
    mount({unmapped: [], clothMap: [], loaded: false});
    expect(document.querySelectorAll('#cm-unmapped tbody tr, #cm-map tbody tr')).toHaveLength(0);
  });
});

describe('Interactions', () => {
  it('links using the typed article and trims whitespace, like the legacy input read', () => {
    const {unmappedBody, link} = mount({unmapped, clothMap: [], loaded: true});
    const row = unmappedBody.querySelectorAll('tr')[0];
    fireEvent.change(row.querySelector('input')!, {target: {value: '  P900  '}});
    fireEvent.click(row.querySelector('button')!);
    expect(link).toHaveBeenCalledWith('X144', 'P900');
  });
  it('passes an empty trimmed value through unchanged, leaving validation to the controller', () => {
    const {unmappedBody, link} = mount({unmapped, clothMap: [], loaded: true});
    fireEvent.click(unmappedBody.querySelectorAll('tr')[0].querySelector('button')!);
    expect(link).toHaveBeenCalledWith('X144', '');
  });
  it('unlinks the clicked row by its cloth code', () => {
    const {mapBody, unlink} = mount({unmapped: [], clothMap, loaded: true});
    fireEvent.click(mapBody.querySelectorAll('tr')[1].querySelector('button')!);
    expect(unlink).toHaveBeenCalledWith('X101');
  });
});
