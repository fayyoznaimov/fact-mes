import { createRef } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ReportWorkflow, type WorkflowHandle } from './ReportWorkflow';
import type { CheckedDocument } from './DocumentBody';
import type { PeriodData } from './period';

export const periodFixture:PeriodData={rows:[{loom:'D1',days:2,shifts:6,designs:['D327'],gsm:[420],effic:75,picks:100000,rows:30,towels:60,towels_known:true,kg:38.1,pile:5,weft:4,ground:3,other:2}],
  totals:{looms:1,days:2,shifts:6,effic:75,picks:100000,rows:30,towels:60,towels_known:true,kg:38.1,pile:5,weft:4,ground:3,other:2},days_without_report:[]};
const checked:CheckedDocument={type:'report',title:'Производственный отчёт',type_title:'Отчёт',checksum:'first',errors:[],warnings:['Неполные данные'],changes:[],summary:periodFixture.totals,result:periodFixture};
const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
function start(){
  const ref=createRef<WorkflowHandle>(),props={expire:vi.fn(),notify:vi.fn(),openDocument:vi.fn(),exportBusy:vi.fn(),download:vi.fn()};
  const fetch=vi.fn<typeof globalThis.fetch>();vi.stubGlobal('fetch',fetch);
  const mounted=render(<ReportWorkflow ref={ref} {...props}/>);return {ref,fetch,...props,...mounted};
}
beforeEach(()=>{
  Object.defineProperties(HTMLDialogElement.prototype,{
    showModal:{configurable:true,value:function(this:HTMLDialogElement){this.open=true;}},
    close:{configurable:true,value:function(this:HTMLDialogElement){if(this.open){this.open=false;this.dispatchEvent(new Event('close'));}}},
  });
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it('loads a period, displays its table and opens confirmation for those exact dates',async()=>{
  const {ref,fetch}=start();fetch.mockResolvedValueOnce(reply(periodFixture)).mockResolvedValueOnce(reply(checked));
  await act(async()=>{ref.current!.period('2026.09.24','2026.09.25');});
  const dialog=document.getElementById('react-period')!;
  expect(dialog).toHaveAttribute('open');expect(within(dialog).getByRole('heading')).toHaveTextContent('24.09.2026 – 25.09.2026');
  expect(within(dialog).getByRole('table')).toHaveTextContent('D327');
  await act(async()=>{fireEvent.click(within(dialog).getByText('Утвердить отчёт…'));});
  expect(JSON.parse(String(fetch.mock.calls[1][1]!.body))).toEqual({type:'report',payload:{from:'2026.09.24',to:'2026.09.25'}});
  expect(document.getElementById('react-doc')).toHaveAttribute('open');
});
it('rejects missing dates and displays API errors without a confirmation button',async()=>{
  const {ref,fetch,notify}=start();act(()=>ref.current!.period('',''));
  expect(fetch).not.toHaveBeenCalled();expect(notify).toHaveBeenCalledWith('Укажите период отчёта',true);
  fetch.mockResolvedValueOnce(reply({error:'Нет данных'},400));
  await act(async()=>ref.current!.period('2026.09.24','2026.09.25'));
  expect(screen.getByText('Нет данных')).toBeInTheDocument();expect(screen.queryByText('Утвердить отчёт…')).toBeNull();
});
it('blocks posting until warnings are acknowledged and sends the preview checksum and comment',async()=>{
  const {ref,fetch,notify}=start();fetch.mockResolvedValueOnce(reply(checked)).mockResolvedValueOnce(reply({id:7,number:'ОТЧ-7'}));
  let result!:Promise<unknown>;await act(async()=>{result=ref.current!.confirm('report',{from:'2026.09.24',to:'2026.09.25'});});
  const post=screen.getByRole('button',{name:'Провести'});expect(post).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));fireEvent.change(screen.getByLabelText('Комментарий к документу'),{target:{value:'Проверено'}});
  await act(async()=>fireEvent.click(post));expect(await result).toEqual({id:7,number:'ОТЧ-7'});
  expect(JSON.parse(String(fetch.mock.calls[1][1]!.body))).toMatchObject({checksum:'first',comment:'Проверено'});
  expect(notify).toHaveBeenCalledWith('Проведён документ ОТЧ-7',false);
});
it('a conflict replaces the preview and requires acknowledgment again',async()=>{
  const {ref,fetch}=start();fetch.mockResolvedValueOnce(reply(checked))
    .mockResolvedValueOnce(reply({error:'Данные изменились',preview:{...checked,checksum:'second'}},409))
    .mockResolvedValueOnce(reply({id:8,number:'ОТЧ-8'}));
  let result!:Promise<unknown>;await act(async()=>{result=ref.current!.confirm('report',{});});
  fireEvent.click(screen.getByRole('checkbox'));await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Провести'})));
  expect(screen.getByText('Данные изменились')).toBeInTheDocument();expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('button',{name:'Провести'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Провести'})));
  expect(JSON.parse(String(fetch.mock.calls[2][1]!.body)).checksum).toBe('second');expect(await result).toMatchObject({id:8});
});
it.each([{errors:['Ошибка ввода']},{may_post:false}])('prevents posting with invalid data or insufficient rights: %j',async patch=>{
  const {ref,fetch}=start();fetch.mockResolvedValueOnce(reply({...checked,...patch}));
  await act(async()=>{void ref.current!.confirm('report',{});});
  const button=screen.getByText('Провести');expect(button).toBeDisabled();fireEvent.click(button);expect(fetch).toHaveBeenCalledOnce();
});
it('cancels preview without allowing a late response to reopen the dialog',async()=>{
  const {ref,fetch}=start();let finish!:(value:Response)=>void;fetch.mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  let result!:Promise<unknown>;act(()=>{result=ref.current!.confirm('report',{});});
  act(()=>{(document.getElementById('react-doc') as HTMLDialogElement).close();});
  expect(await result).toBeNull();expect(fetch.mock.calls[0][1]!.signal!.aborted).toBe(true);
  await act(async()=>finish(reply(checked)));expect(document.getElementById('react-doc')).not.toHaveAttribute('open');
});
it('prevents duplicate submission and cancellation while a document is being posted',async()=>{
  const {ref,fetch}=start();let finish!:(value:Response)=>void;
  fetch.mockResolvedValueOnce(reply({...checked,warnings:[]})).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  await act(async()=>{void ref.current!.confirm('report',{});});
  fireEvent.click(screen.getByRole('button',{name:'Провести'}));fireEvent.click(screen.getByRole('button',{name:'Провести'}));
  expect(fetch).toHaveBeenCalledTimes(2);expect(screen.getByText('Вернуться к правке')).toBeDisabled();
  const event=new Event('cancel',{cancelable:true});document.getElementById('react-doc')!.dispatchEvent(event);expect(event.defaultPrevented).toBe(true);
  await act(async()=>finish(reply({id:9,number:'ОТЧ-9'})));
});
it('exports the captured date only after generation and prevents duplicate exports',async()=>{
  const {ref,fetch,download,exportBusy}=start();let finish!:(value:Response)=>void;fetch.mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  act(()=>{ref.current!.excel('2026.09.24');ref.current!.excel('2026.09.25');});
  expect(fetch).toHaveBeenCalledOnce();expect(download).not.toHaveBeenCalled();expect(exportBusy).toHaveBeenCalledWith(true);
  await act(async()=>finish(reply({ok:true})));expect(download).toHaveBeenCalledExactlyOnceWith('/api/excel?day=2026.09.24');expect(exportBusy).toHaveBeenLastCalledWith(false);
});
it('does not download on export failure and allows retry',async()=>{
  const {ref,fetch,download,notify}=start();fetch.mockResolvedValueOnce(reply({ok:false,log:'Нет отчёта'})).mockResolvedValueOnce(reply({ok:true}));
  await act(async()=>ref.current!.excel('2026.09.24'));expect(download).not.toHaveBeenCalled();expect(notify).toHaveBeenCalledWith('Excel не собрался: Нет отчёта',true);
  await act(async()=>ref.current!.excel('2026.09.24'));expect(download).toHaveBeenCalledOnce();
});
