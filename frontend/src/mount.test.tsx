import { act, fireEvent } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { mountReport } from './mount';
import { reportMarkup } from './test/legacy';
import type { Snapshot } from './features/report/model';

let dispose:(()=>void)|undefined;
afterEach(()=>{if(dispose)act(dispose);dispose=undefined;document.body.innerHTML='';localStorage.clear();vi.unstubAllGlobals();});
function start(){
  document.body.innerHTML=reportMarkup+'<dialog id="ls-dlg"></dialog><dialog id="archive-dlg"><input value="keep me"></dialog>';
  document.querySelector('#rep-day')!.innerHTML='<option value="2026.09.25">25.09.2026</option>';
  (document.querySelector('#rp-from') as HTMLInputElement).value='2026-09-01';
  let state:Snapshot={rows:[{loom:'D1',rpm:480}],day:'2026.09.25',filters:{},sort:null,hidden:[],flag:'all',setupEdit:true,exportAllowed:true};
  const snapshot=()=>({...state,day:(document.querySelector('#rep-day') as HTMLSelectElement).value});
  const setup=vi.fn().mockResolvedValue(undefined);
  document.querySelector<HTMLDialogElement>('#ls-dlg')!.showModal=vi.fn();
  document.querySelector('#tab-report')!.classList.add('hidden');
  window.FactReportLegacy={snapshot,prepareSetup:setup,notify:vi.fn(),openDocument:vi.fn(),full:vi.fn(),stick:vi.fn(),approved:vi.fn(),
    publish:rows=>{state={...state,rows};},expire:vi.fn(),error:vi.fn()};
  act(()=>{dispose=mountReport();});
  return {setup,refresh:async(rows:Snapshot['rows'])=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({rows}),{headers:{'Content-Type':'application/json'}})));
    await act(async()=>{await window.FactReactReport!.load(false);});
  }};
}
it('mounts into the original shell once and preserves dialog nodes and edited date ranges',async()=>{
  const a=start();const dialog=document.getElementById('ls-dlg');
  fireEvent.change(document.getElementById('rp-from')!,{target:{value:'2026-09-12'}});
  await act(async()=>{fireEvent.click(document.querySelector('[data-loom="D1"]')!);});expect(a.setup).toHaveBeenCalledOnce();
  expect(document.querySelector('#ls-title')).toHaveTextContent('Заправка станка D1');
  await a.refresh([{loom:'D2',rpm:510}]);
  expect(document.getElementById('ls-dlg')).toBe(dialog);
  expect(document.querySelector('#archive-dlg input')).toHaveValue('keep me');
  expect(document.getElementById('rp-from')).toHaveValue('2026-09-12');
  expect(document.querySelectorAll('#rep-day')).toHaveLength(1);
  expect(document.querySelector('#rep-table tbody')).toHaveTextContent('D2');
});
it('accepts async day loading and retains filters after refresh',async()=>{
  const a=start();act(()=>window.FactReactReport!.setDays(['2026.09.26','2026.09.25']));
  expect(document.querySelector('#rep-day')).toHaveValue('2026.09.26');
  fireEvent.change(document.querySelector('input[data-i="5"]')!,{target:{value:'D1'}});
  await a.refresh([{loom:'D1'},{loom:'D2'}]);
  expect(document.querySelectorAll('#rep-table tbody tr')).toHaveLength(1);
  expect(document.querySelector('#rep-count')).toHaveTextContent('Показано 1 из 2');
});
