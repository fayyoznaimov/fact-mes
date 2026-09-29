import { act, fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SetupDialog } from './SetupDialog';
import type { Row } from './model';

const row:Row={loom:'D1',cloth:'FABRIC',design:'D327',gsm:420,ppt:3200,weight_kg:.635,panels:2,
  setup:{ppt:3300,pile_lot:'manual-lot',set_by:'Мастер',from_day:'2026.09.20'}};
Object.assign(row,{yarn_by:{pile:{yarn:'20/2',lot:'ref-lot'}}});
function mount(confirm=vi.fn().mockResolvedValue(null)){
  document.body.innerHTML='<dialog id="ls-dlg"></dialog>';
  const target=document.querySelector<HTMLDialogElement>('dialog')!;
  target.showModal=vi.fn(()=>{target.open=true;});
  target.close=vi.fn(()=>{target.open=false;target.dispatchEvent(new Event('close'));});
  const props={target,row,rows:[row,{loom:'D2',cloth:'FABRIC'},{loom:'J1',cloth:'OTHER'}],day:'2026.09.25',session:1,
    confirm,error:vi.fn(),close:vi.fn(),refresh:vi.fn()};
  render(<SetupDialog {...props}/>);return props;
}
afterEach(()=>{cleanup();document.body.innerHTML='';});
it('keeps all nine yarn positions and manual-over-reference defaults',()=>{
  const p=mount();expect(p.target.showModal).toHaveBeenCalledOnce();
  expect(document.querySelectorAll('#ls-yarns tr')).toHaveLength(9);
  expect(screen.getByLabelText('PPT — прокидки на ряд')).toHaveValue('3300');
  expect(screen.getByLabelText('Ворс (Pile): пряжа')).toHaveValue('20/2');
  expect(screen.getByLabelText('Ворс (Pile): лот')).toHaveValue('manual-lot');
  expect(document.getElementById('ls-note')).toHaveTextContent('20.09.2026');
});
it('passes exact edited strings, effective time and selected matching looms for confirmation',async()=>{
  const confirm=vi.fn().mockResolvedValue({id:1}),p=mount(confirm);
  fireEvent.change(screen.getByLabelText('Вес штуки, кг'),{target:{value:'635 г'}});
  fireEvent.change(screen.getByLabelText('Время начала заправки'),{target:{value:'15:30'}});
  fireEvent.click(document.getElementById('ls-same')!);
  // The existing yarn picker writes the native value before dispatching input/change.
  const lot=screen.getByLabelText('Ворс (Pile): лот') as HTMLInputElement;lot.value='picker-lot';fireEvent.input(lot);
  await act(async()=>{fireEvent.click(screen.getByText('Проверить и провести…'));});
  expect(confirm).toHaveBeenCalledOnce();const payload=confirm.mock.calls[0][0];
  expect(payload).toMatchObject({from_day:'2026.09.25',effective_at:'2026-09-25T15:30:00+05:00',rows:[
    {loom:'D1',values:{ppt:'3300',weight_kg:'635 г',pile_lot:'picker-lot'}},
    {loom:'D2',values:{ppt:'3300',weight_kg:'635 г',pile_lot:'picker-lot'}},
  ]});expect(p.refresh).toHaveBeenCalledOnce();expect(p.target.close).toHaveBeenCalledOnce();
});
it('retains entered values when document confirmation is cancelled',async()=>{
  const p=mount();fireEvent.change(screen.getByLabelText('Дизайн'),{target:{value:'edited'}});
  await act(async()=>{fireEvent.click(screen.getByText('Проверить и провести…'));});
  expect(p.target.close).not.toHaveBeenCalled();expect(p.refresh).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Дизайн')).toHaveValue('edited');
});
it('requires effective time and prevents a duplicate confirmation while busy',async()=>{
  let finish!:(value:unknown)=>void;const confirm=vi.fn(()=>new Promise(resolve=>{finish=resolve;})),p=mount(confirm);
  fireEvent.change(screen.getByLabelText('Время начала заправки'),{target:{value:''}});
  fireEvent.click(screen.getByText('Проверить и провести…'));expect(p.error).toHaveBeenCalledWith('Укажите время начала заправки');expect(confirm).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Время начала заправки'),{target:{value:'07:00'}});
  fireEvent.click(screen.getByText('Проверить и провести…'));expect(screen.getByText('Проверить и провести…')).toBeDisabled();
  fireEvent.click(screen.getByText('Проверить и провести…'));expect(confirm).toHaveBeenCalledOnce();
  await act(async()=>finish(null));expect(screen.getByText('Проверить и провести…')).toBeEnabled();
});
