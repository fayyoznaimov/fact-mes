import { createRoot } from 'react-dom/client';
import { createRef } from 'react';
import { flushSync } from 'react-dom';
import { Report, type Actions, type Targets } from './features/report/Report';
import type { Snapshot } from './features/report/model';
import { ReportController, requestReport } from './features/report/controller';
import { SetupDialog } from './features/report/SetupDialog';
import { ReportWorkflow, type WorkflowHandle } from './features/report/ReportWorkflow';

declare global {
  interface Window {
    FactReportLegacy: Omit<Actions,'load'|'setView'|'setup'|'period'|'excel'> & {snapshot:()=>Snapshot;
      publish:(rows:Snapshot['rows'])=>void;expire:()=>void;error:(message:string)=>void;
      prepareSetup:()=>Promise<void>;notify:(message:string,error?:boolean)=>void;openDocument:(id:number)=>void};
    FactReactReport?: {update:()=>void;setDays:(days:string[])=>void;load:(autoSkip?:boolean)=>Promise<void>};
  }
}
export function mountReport() {
  const legacy=window.FactReportLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка отчёта');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента отчёта: '+selector);return el;
  };
  const targets:Targets={bar:element('#tab-report > .bar'),table:element('#rep-table'),tiles:element('#rep-tiles'),strip:element('#rep-strip')};
  const days=Array.from(element<HTMLSelectElement>('#rep-day').options).map(o=>o.value);
  const snapshot=legacy.snapshot();
  const range={from:element<HTMLInputElement>('#rp-from').value,to:element<HTMLInputElement>('#rp-to').value};
  const setupTarget=element<HTMLDialogElement>('#ls-dlg');
  setupTarget.replaceChildren();
  let setupRow:Snapshot['rows'][number]|null=null,setupSession=0;
  Object.values(targets).forEach(target=>target.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactReport='';document.body.appendChild(host);
  const root=createRoot(host);
  const workflow=createRef<WorkflowHandle>();
  let alive=true;
  const closeSetup=()=>{setupRow=null;render();};
  const refresh=()=>{void controller.load(false);};
  const render=()=>flushSync(()=>root.render(<>
    <Report state={controller.state} days={controller.days} range={range} actions={actions} targets={targets}/>
    <SetupDialog target={setupTarget} row={setupRow} rows={controller.state.rows} day={controller.state.day} session={setupSession}
      confirm={payload=>workflow.current!.confirm('setup',payload)} error={legacy.error} close={closeSetup} refresh={refresh}/>
    <ReportWorkflow ref={workflow} expire={legacy.expire} notify={legacy.notify} openDocument={legacy.openDocument}
      exportBusy={busy=>{controller.state={...controller.state,exportBusy:busy};render();}}/>
  </>));
  const controller=new ReportController(snapshot,days,{
    request:(day,signal)=>requestReport(day,signal,legacy.expire),changed:render,
    publish:legacy.publish,error:legacy.error,
    storage:{getItem:key=>localStorage.getItem(key),setItem:(key,v)=>localStorage.setItem(key,v)},
  });
  const actions:Actions={...legacy,setView:view=>controller.setView(view),load:day=>{void controller.load(false,day);},
    period:()=>workflow.current!.period(element<HTMLInputElement>('#rp-from').value.replace(/-/g,'.'),element<HTMLInputElement>('#rp-to').value.replace(/-/g,'.')),
    excel:()=>{if(controller.state.exportAllowed&&!controller.state.loading)workflow.current!.excel(controller.state.day);},setup:loom=>{
    if(!controller.state.setupEdit||controller.state.loading)return;
    const day=controller.state.day;
    void legacy.prepareSetup().then(()=>{
      if(!alive||controller.state.loading||controller.state.day!==day||!controller.state.setupEdit)return;
      setupRow=controller.state.rows.find(r=>r.loom===loom)||null;setupSession++;render();
    }).catch(e=>legacy.error('Заправка не открылась: '+String(e)));
  }};
  const update=()=>{
    const {setupEdit,exportAllowed}=legacy.snapshot();
    controller.state={...controller.state,setupEdit,exportAllowed};render();
  };
  window.FactReactReport={
    update,
    setDays:next=>{controller.setDays(next);update();},
    load:autoSkip=>controller.load(autoSkip),
  };
  render();
  const language=()=>window.FactReactReport?.update();
  window.addEventListener('mes-language-change',language);
  if(days.length && !element('#tab-report').classList.contains('hidden'))void controller.load(true);
  return ()=>{alive=false;controller.dispose();window.removeEventListener('mes-language-change',language);delete window.FactReactReport;root.unmount();host.remove();};
}
