import { useState } from 'react';
import { render, fireEvent, cleanup, screen } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { Report, type Actions, type Targets } from './Report';
import { COLUMNS, G_SETUP, G_MEND, SHIFT_GROUPS, type Snapshot, type Row } from './model';
import { legacyReport, reportOutput, reportMarkup } from '../../test/legacy';

const rows: Row[] = ['D1','D2','J1','J14'].map((loom,i) => ({
  ...Object.fromEntries(COLUMNS.map((c,j) => [c.k, (i * 37 + j * 13) % 140])),
  loom, sr:i+1, design:i%2?'D327':'J156', rpm:i===3?null:480+i*7, weight_kg:.256+i*.01,
  prod100_kg:i===3?null:120, achieved_kg:i===3?null:80+i*5, picks:300000+i*1000,
  ppt:i===3?null:3200, ppt_est:3300, ppt_fact:3500, ppt_gap:9.375, ppt_spread:2.31,
  ppt_note:'Проверка < & "', y_pile:'20/2 · ЛОТ-1', y_ground:'16/1 · 2026',
  _red:i===0, _yel:i===1,
  setup:i===1?{ppt:3200,weight_kg:.266,pile_lot:'ЛОТ-1',weft4_yarn:'20/2',set_by:'Мастер < & "',from_day:'2026.09.24'}:null,
}));
const initial: Snapshot = {rows, filters:{}, sort:null, hidden:[], flag:'all', day:'2026.09.25',setupEdit:true,exportAllowed:true};
function mount(state:Snapshot=initial) {
  document.body.innerHTML = reportMarkup;
  const targets:Targets={bar:document.querySelector('#tab-report > .bar')!,table:document.querySelector('#rep-table')!,tiles:document.querySelector('#rep-tiles')!,strip:document.querySelector('#rep-strip')!};
  Object.values(targets).forEach(t=>t.replaceChildren());
  const actions:Actions={setView:vi.fn(),load:vi.fn(),setup:vi.fn(),full:vi.fn(),stick:vi.fn(),period:vi.fn(),approved:vi.fn(),excel:vi.fn()};
  function Harness(){const [current,set]=useState(state);actions.setView=v=>set(s=>({...s,...v}));return <Report state={current} days={['2026.09.25','2026.09.24']} range={{from:'2026-09-01',to:'2026-09-27'}} targets={targets} actions={actions}/>;}
  render(<Harness/>);return actions;
}
afterEach(()=>{cleanup();document.body.innerHTML='';document.documentElement.lang='ru';});
describe('Parity with the original HTML report',()=>{
  it.each(['ru','en'])('preserves all 45 columns, cell text, colours, tooltips and totals (%s)',lang=>{
    document.documentElement.lang=lang;mount();
    expect(document.querySelectorAll('#rep-table tr.cols th')).toHaveLength(45);
    expect(reportOutput(document)).toEqual(reportOutput(legacyReport(initial,lang)));
  });
  it.each([
    {filters:{5:'J1-J14'}},{filters:{2:'>=490',6:'d327'}},{filters:{8:'0,26-0,3'}},
    {filters:{2:'nonsense'}},{filters:{11:'лот-1'},hidden:[G_SETUP]},
    {filters:{5:'missing'}},{flag:'red'},{flag:'warn'},
    {sort:{i:2,dir:-1}},{sort:{i:2,dir:1}},{sort:{i:5,dir:1}},
    {setupEdit:false},{rows:[]},
  ] as Partial<Snapshot>[])('matches filtering, sorting, permissions and empty results: %j',patch=>{
    const state={...initial,...patch};mount(state);
    expect(reportOutput(document)).toEqual(reportOutput(legacyReport(state)));
  });
  it('preserves every combination of collapsed groups',()=>{
    const groups=[G_SETUP,G_MEND,...SHIFT_GROUPS];
    for(let mask=0;mask<128;mask++){
      const state={...initial,rows:rows.slice(0,1),hidden:groups.filter((_,i)=>mask&(1<<i))};
      mount(state);expect(reportOutput(document),`collapse mask ${mask}`).toEqual(reportOutput(legacyReport(state)));cleanup();
    }
  },20000);
  it('preserves colour thresholds and zero/missing cells',()=>{
    for(const n of [null,'',0,1,16,20,21,29,30,40,41,45,49,50,60,61,69,70,79,80,89,90,91,120,121]){
      const state={...initial,rows:[{...Object.fromEntries(COLUMNS.filter(c=>!c.text).map(c=>[c.k,n])),loom:'D1'}]};
      mount(state);expect(reportOutput(document),`value ${n}`).toEqual(reportOutput(legacyReport(state)));cleanup();
    }
  });
});
describe('Report interactions',()=>{
  it('filters, marks invalid expressions, keeps hidden filters and resets without expanding groups',()=>{
    mount();fireEvent.change(screen.getByLabelText('Фильтр: Заправка, Ворс · лот'),{target:{value:'absent'}});
    expect(screen.getByText('Под фильтры не попал ни один станок')).toBeInTheDocument();
    fireEvent.click(document.querySelector('#rg-setup')!);
    expect(document.querySelector('#rep-count')).toHaveTextContent('фильтр стоит и в свёрнутой группе');
    fireEvent.click(screen.getByText('Сбросить фильтры и сортировку'));
    expect(document.querySelectorAll('#rep-table tbody tr')).toHaveLength(4);
    expect(document.querySelector('#rg-setup')).not.toBeChecked();
    fireEvent.change(screen.getByLabelText('Фильтр: Об/мин'),{target:{value:'wrong'}});
    expect(screen.getByLabelText('Фильтр: Об/мин')).toHaveClass('bad-in');
    expect(document.querySelectorAll('#rep-table tbody tr')).toHaveLength(4);
  });
  it('cycles sorting three times and keeps missing values last',()=>{
    mount();const heading=document.querySelector('th[data-i="2"]')!;
    const looms=()=>Array.from(document.querySelectorAll('td.edit-loom')).map(e=>e.getAttribute('data-loom'));
    fireEvent.click(heading);expect(looms()).toEqual(['J1','D2','D1','J14']);
    fireEvent.keyDown(heading,{key:'Enter'});expect(looms()).toEqual(['D1','D2','J1','J14']);
    fireEvent.click(heading);expect(heading).toHaveAttribute('aria-sort','none');
  });
  it('calls existing day, setup, period, approval, Excel and fullscreen actions',()=>{
    const a=mount();fireEvent.click(document.querySelector('[data-loom="D1"]')!);expect(a.setup).toHaveBeenCalledWith('D1');
    fireEvent.change(screen.getByLabelText('День'),{target:{value:'2026.09.24'}});expect(a.load).toHaveBeenCalledWith('2026.09.24');
    for(const [id,key] of [['rp-go','period'],['rp-list','approved'],['rep-excel','excel']] as const){fireEvent.click(document.getElementById(id)!);expect(a[key]).toHaveBeenCalledOnce();}
    fireEvent.click(document.getElementById('rep-full')!);expect(a.full).toHaveBeenCalledWith(true);
    fireEvent.click(document.getElementById('rep-strip-exit')!);expect(a.full).toHaveBeenCalledWith(false);
  });
  it('respects read-only setup and export rights',()=>{
    const a=mount({...initial,setupEdit:false,exportAllowed:false});
    expect(document.querySelectorAll('.edit-loom')).toHaveLength(0);
    expect(screen.getByText('Скачать Excel')).toBeDisabled();
    fireEvent.click(screen.getByText('D1'));expect(a.setup).not.toHaveBeenCalled();
  });
  it('shows mixed shift state after collapsing a single group',()=>{
    mount();fireEvent.click(document.querySelector('th[data-g="Efficiency"]')!);
    expect((document.querySelector('#rg-shift') as HTMLInputElement).indeterminate).toBe(true);
    expect(document.querySelectorAll('#rep-table tr.cols th')).toHaveLength(42);
    fireEvent.click(document.querySelector('#rg-shift')!);
    expect(document.querySelectorAll('#rep-table tr.cols th')).toHaveLength(45);
  });
  it('blocks setup and export while the selected day is still loading',()=>{
    mount({...initial,loading:true});
    expect(document.getElementById('rep-table')).toHaveAttribute('aria-busy','true');
    expect(document.querySelectorAll('.edit-loom')).toHaveLength(0);
    expect(screen.getByText('Скачать Excel')).toBeDisabled();
  });
});
